"""Entry point for the life agent.

Phase 5: Adds timestamp injection on every user message, scheduling tools,
and runs the scheduler concurrently with the Telegram bot via asyncio.
"""

import asyncio
import logging
import sys

import anthropic

# Ensure UTF-8 output (emoji-safe on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

from telegram.ext import Application

import claude_client
import conversation
import scheduler
import telegram_bot
import utils


async def on_message(user_text: str) -> str:
    """Handle an incoming Telegram message and return Claude's reply."""
    system_prompt = utils.build_system_prompt()
    history = conversation.load_history()

    # Inject timestamp so Claude always knows the current time
    stamped = (
        f"[Current time: {utils.format_datetime(utils.now_local())}]\n"
        f"[Message from user]: {user_text}"
    )

    conversation.append_message("user", stamped, source="telegram")

    try:
        reply = await asyncio.to_thread(
            claude_client.send_message,
            system_prompt=system_prompt,
            history=history,
            user_message=stamped,
        )
    except anthropic.AuthenticationError:
        logger.error("Anthropic authentication error — check API key and account credits")
        return (
            "⚠️ Couldn't reach Claude: authentication failed. "
            "Check that your API key is valid and your account has credits."
        )
    except anthropic.RateLimitError:
        logger.error("Anthropic rate limit exceeded after retry")
        return "⚠️ Couldn't reach Claude: rate limit hit. Try again in a moment."
    except anthropic.APIConnectionError:
        logger.error("Anthropic connection error after retry")
        return "⚠️ Couldn't reach Claude: network error. Check your internet connection."
    except anthropic.APIStatusError as e:
        logger.error("Anthropic API error after retry: status=%d", e.status_code)
        return f"⚠️ Couldn't reach Claude: API error (HTTP {e.status_code}). Try again shortly."
    except Exception:
        logger.exception("Unexpected error handling message")
        return "⚠️ Something went wrong on my end. Check the logs."

    conversation.append_message("assistant", reply)
    return reply


async def post_init(app: Application) -> None:
    """Start the scheduler as a background task once the bot is ready."""
    app.create_task(scheduler.run(app.bot))
    logger.info("Scheduler task created")


def main() -> None:
    logger.info("Starting life agent (Phase 5 — with scheduling)")
    app = telegram_bot.build_application(on_message, post_init=post_init)
    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
