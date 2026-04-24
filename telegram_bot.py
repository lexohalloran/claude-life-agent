import logging
from typing import Callable, Awaitable

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

import config

logger = logging.getLogger(__name__)

# Type aliases
MessageCallback = Callable[[str], Awaitable[str]]
PostInitCallback = Callable[[Application], Awaitable[None]]


def build_application(
    on_message: MessageCallback,
    post_init: PostInitCallback | None = None,
) -> Application:
    """Build and return the Telegram Application.

    on_message: async function that accepts the user's text and returns
    Claude's reply. Wired in by main.py so this module stays decoupled
    from claude_client.
    """
    builder = Application.builder().token(config.TELEGRAM_BOT_TOKEN)
    if post_init:
        builder = builder.post_init(post_init)
    app = builder.build()

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None or update.message is None:
            return

        chat_id = update.effective_chat.id

        # Allowlist check
        if chat_id != config.TELEGRAM_ALLOWED_CHAT_ID:
            logger.warning("Rejected message from unauthorized chat_id=%d", chat_id)
            return

        user_text = update.message.text or ""
        if not user_text.strip():
            return

        logger.info("Received message from chat_id=%d (%d chars)", chat_id, len(user_text))

        # Show typing indicator while Claude thinks
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        reply = await on_message(user_text)

        await update.message.reply_text(reply)
        logger.info("Sent reply (%d chars) to chat_id=%d", len(reply), chat_id)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
