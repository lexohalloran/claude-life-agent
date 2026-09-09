"""Background scheduler: fires scheduled messages when their time comes.

The loop:
  1. Read schedule.json, find the earliest pending entry.
  2. Sleep until that time (rechecking at least every 60 seconds so
     newly-added entries are picked up quickly).
  3. When an entry fires: build context, call Claude, send via Telegram,
     log to conversation history, remove from schedule.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
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
            await _maybe_run_maintenance(bot)
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
    """Send a scheduled entry, calling Claude to compose it unless it's direct."""
    if entry.get("direct_text"):
        await _fire_direct(bot, entry)
        return

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
            source="scheduled",
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


MAINTENANCE_PROMPT = """\
[Current time: {now}]
[Automatic daily maintenance. This is not a message from the user — they did not
write it and are not waiting on a reply. Your text response will be discarded and
shown to nobody. The only way to reach the user is the send_message_to_user tool.]

You have three jobs.

1. Review your scheduled messages.
   Call list_scheduled_messages. Weighing what you know from your notes, the life
   doc, and yesterday's conversation below, decide whether each one still makes
   sense. Cancel reminders for routines the user has stopped. If a recurring
   series is running out soon, extend it or schedule a check-in asking whether
   they still want it — don't let a series lapse silently, since the user may not
   notice until they've missed something. If you cancel anything, tell the user
   what you cancelled and why.

2. Summarize yesterday ({yesterday}).
   Yesterday's messages are below. Call write_day_summary for that date. This
   summary is what you will still have once the raw messages age out of your
   context, so capture what matters: emotional tone, ongoing threads, things you
   learned about the user, commitments made or completed. Not a transcript. If
   there was no conversation, say so in one line.

3. Consolidate your notes.
   Call read_claude_notes, then edit_claude_notes. Merge duplicate facts, remove
   information that later events have made stale, and tighten wording. This is
   your one scheduled chance to review the whole file critically rather than
   appending to it, and nothing else stops it growing without bound.

Only message the user if something genuinely warrants their attention: a
cancellation you made, or a question you need answered. Most maintenance runs
should finish without sending anything.

[Yesterday's conversation ({yesterday})]:
{transcript}
"""


async def _maybe_run_maintenance(bot: Bot) -> None:
    """Run the daily maintenance pass if it's due and hasn't run today."""
    now = utils.now_local()
    if now.hour < config.MAINTENANCE_HOUR:
        return

    today = now.date().isoformat()
    if _read_maintenance_state().get("last_run_date") == today:
        return

    # Claim the day before running. A persistent failure should cost one
    # maintenance pass, not retry every minute until midnight.
    _write_maintenance_state({"last_run_date": today})
    logger.info("Running daily maintenance pass for %s", today)

    try:
        await _run_maintenance(bot, now)
    except Exception:
        logger.exception("Daily maintenance pass failed")


async def _run_maintenance(bot: Bot, now: datetime) -> None:
    tools.drain_outbox()  # discard anything stranded by a previous failed run

    yesterday = (now.date() - timedelta(days=1)).isoformat()
    messages = conversation.messages_for_date(yesterday)
    transcript = (
        "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        or "(no conversation yesterday)"
    )

    trigger_text = MAINTENANCE_PROMPT.format(
        now=utils.format_datetime(now),
        yesterday=yesterday,
        transcript=transcript,
    )

    reply = await asyncio.to_thread(
        claude_client.send_message,
        system_prompt=utils.build_system_prompt(),
        history=[],
        user_message=trigger_text,
        source="maintenance",
        tool_schemas=tools.MAINTENANCE_TOOL_SCHEMAS,
    )
    logger.info("Maintenance finished; discarding text reply (%d chars)", len(reply))

    outbox = tools.drain_outbox()
    if not outbox:
        logger.info("Maintenance had nothing to say")
        return

    # Log as a single assistant turn (paired with a trigger) so the exchange
    # reads correctly if the user replies, even though it goes out as several
    # Telegram messages.
    conversation.append_message(
        "user", f"[Daily maintenance pass, {now.date().isoformat()}]", source="maintenance"
    )
    conversation.append_message("assistant", "\n\n".join(outbox), source="maintenance")

    for text in outbox:
        await bot.send_message(chat_id=config.TELEGRAM_ALLOWED_CHAT_ID, text=text)
    logger.info("Maintenance sent %d message(s) to the user", len(outbox))


def _read_maintenance_state() -> dict:
    if not config.MAINTENANCE_STATE_FILE.exists():
        return {}
    try:
        text = config.MAINTENANCE_STATE_FILE.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read maintenance state: %s", e)
        return {}


def _write_maintenance_state(state: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.MAINTENANCE_STATE_FILE.write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )


async def _fire_direct(bot: Bot, entry: dict) -> None:
    """Send a fixed-text scheduled message without consulting Claude.

    Logs a synthetic trigger alongside the message, mirroring the Claude path:
    it tells future context that this went out mechanically, and keeps the log
    in user/assistant pairs so a trimmed history never starts mid-exchange.
    """
    text = entry["direct_text"]
    trigger_text = (
        f"[Current time: {utils.format_datetime(utils.now_local())}]\n"
        f"[Scheduled reminder fired automatically — sent verbatim, you were not consulted]"
    )
    conversation.append_message("user", trigger_text, source="scheduled-direct")
    conversation.append_message("assistant", text, source="scheduled-direct")

    await bot.send_message(chat_id=config.TELEGRAM_ALLOWED_CHAT_ID, text=text)
    logger.info("Sent direct scheduled message id=%s (%d chars)", entry["id"], len(text))


