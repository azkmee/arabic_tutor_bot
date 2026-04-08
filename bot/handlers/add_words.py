from telegram import Update
from telegram.ext import ContextTypes

from bot import db


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command — queue raw words for processing.

    Usage:
      /add كتاب book
      /add كتاب
      /add (followed by multiple lines)
    """
    text = update.message.text

    # Strip the /add prefix
    raw = text.removeprefix("/add").strip()

    if not raw:
        await update.message.reply_text(
            "Usage: /add كلمة [meaning]\n"
            "Or send multiple words, one per line:\n"
            "/add\n"
            "كتاب book\n"
            "قلم pen"
        )
        return

    # Split by newlines for multi-word input
    lines = [line.strip() for line in raw.split("\n") if line.strip()]

    count = db.add_raw_words(lines, source="telegram")

    await update.message.reply_text(
        f"📝 Queued <b>{count}</b> word{'s' if count != 1 else ''} for processing.\n"
        f"Open Claude Desktop to format and add them.",
        parse_mode="HTML",
    )
