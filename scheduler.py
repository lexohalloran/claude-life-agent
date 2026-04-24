"""Background scheduler: fires scheduled messages when their time comes.

The loop:
  1. Read schedule.json, find the earliest pending entry.
  2. Sleep until that time (rechecking at least every 60 seconds so
     newly-added entries are picked up quickly).
  3. When an entry fires: build context, call Claude, send via Telegram,
     log to conversation history, remove from schedule.
"""

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Bot

import claude_client
import config
import conversation
import tools
import utils

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds between schedule rechecks


async def run(bot: Bot) -> None:
    """Main scheduler loop. Run as a background asyncio task."""
    logger.info("Scheduler started")
    while True:
        try:
            await _tick(bot)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            raise
        except Exception:
            logger.exception("Unexpected error in scheduler tick — continuing")
        await asyncio.sleep(POLL_INTERVAL)


async def _tick(bot: Bot) -> None:
    """Check for due messages and fire any that are ready."""
    schedule = tools._read_schedule()
    if not schedule:
        return

    now = datetime.now(timezone.utc)
    grace = config.SCHEDULER_GRACE_PERIOD_HOURS * 3600
    due = [e for e in schedule if datetime.fromisoformat(e["when"]) <= now]

    for entry in sorted(due, key=lambda e: e["when"]):
        overdue_seconds = (now - datetime.fromisoformat(entry["when"])).total_seconds()

        if overdue_seconds > grace:
            logger.warning(
                "Dropping scheduled message id=%s — overdue by %.1fh (grace=%.1fh)",
                entry["id"], overdue_seconds / 3600, config.SCHEDULER_GRACE_PERIOD_HOURS,
            )
        else:
            late_minutes = int(overdue_seconds // 60)
            logger.info("Firing scheduled message id=%s (overdue by %dm)", entry["id"], late_minutes)
            await _fire(bot, entry, late_minutes=late_minutes)

        # Remove the entry regardless of whether it was fired or dropped
        schedule = tools._read_schedule()
        schedule = [e for e in schedule if e["id"] != entry["id"]]
        tools._write_schedule(schedule)


async def _fire(bot: Bot, entry: dict, late_minutes: int = 0) -> None:
    """Call Claude for a scheduled entry and send the result via Telegram."""
    now = utils.now_local()
    scheduled_at = datetime.fromisoformat(entry["scheduled_at"]).astimezone(
        ZoneInfo(config.TIMEZONE)
    )
    fire_at = datetime.fromisoformat(entry["when"]).astimezone(ZoneInfo(config.TIMEZONE))

    # Build the trigger pseudo-message (matches spec timestamp format)
    late_note = f"\n[Note: this message is firing {late_minutes} minutes late due to downtime]" if late_minutes > 1 else ""
    trigger_text = (
        f"[Current time: {utils.format_datetime(now)}]\n"
        f"[Scheduled trigger, originally set at {utils.format_datetime(scheduled_at)}"
        f" to fire at {utils.format_datetime(fire_at)}]{late_note}\n"
        f"[Context note to self]: {entry['context']}"
    )

    system_prompt = utils.build_system_prompt()
    history = conversation.load_history()

    # Log the trigger as a user-side event before calling Claude
    conversation.append_message("user", trigger_text, source="scheduled")

    try:
        reply = await asyncio.to_thread(
            claude_client.send_message,
            system_prompt=system_prompt,
            history=history,
            user_message=trigger_text,
        )
    except Exception:
        logger.exception("Claude API call failed for scheduled message id=%s", entry["id"])
        await bot.send_message(
            chat_id=config.TELEGRAM_ALLOWED_CHAT_ID,
            text="(Something went wrong with a scheduled message — check the logs.)",
        )
        return

    conversation.append_message("assistant", reply)

    await bot.send_message(chat_id=config.TELEGRAM_ALLOWED_CHAT_ID, text=reply)
    logger.info("Sent scheduled message id=%s (%d chars)", entry["id"], len(reply))


