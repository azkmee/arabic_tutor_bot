from telegram import Update
from telegram.ext import ContextTypes

from bot import db


async def add_passage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_passage — queue passage text for cowork to enrich.

    The full message body after "/add_passage " is taken as a single passage
    (newlines preserved). Cowork later adds tashkeel, splits into sentences,
    and produces per-word glosses.
    """
    text = update.message.text or ""
    raw = text.removeprefix("/add_passage").strip()

    if not raw:
        await update.message.reply_text(
            "Usage: /add_passage <text>\n"
            "Paste a paragraph (newlines OK). Cowork will add tashkeel,\n"
            "split it into sentences, and gloss every word."
        )
        return

    count = db.add_raw_passages([raw], source="telegram")
    await update.message.reply_text(
        f"📖 Queued <b>{count}</b> passage for cowork.\n"
        f"Open Claude Desktop to enrich it.",
        parse_mode="HTML",
    )
