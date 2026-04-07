from telegram import Update
from telegram.ext import ContextTypes

from bot import db


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show learning stats."""
    stats = db.get_stats()

    await update.message.reply_text(
        f"📊 <b>إحصائيات</b> — Your Stats\n"
        f"{'─' * 28}\n"
        f"📚 Total words: {stats['total_words']}\n"
        f"📅 Due today: {stats['due_today']}\n"
        f"🏆 Mastered (level 7+): {stats['mastered']}\n"
        f"📝 Pending raw words: {stats['pending_raw']}\n",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "<b>📖 Arabic Tutor Bot — Commands</b>\n"
        "─" * 28 + "\n"
        "/review — Start a review session now\n"
        "/add كلمة [meaning] — Queue a word for processing\n"
        "/status — View your learning stats\n"
        "/help — Show this message\n"
        "\n"
        "<b>Scheduled Reviews:</b>\n"
        "🌅 Morning (9AM SGT) — 5 vocab + 2 grammar + 1 sentence\n"
        "🌞 Lunch (1PM SGT) — 5 vocab + 2 grammar + 1 sentence\n"
        "🌙 Dinner (8PM SGT) — 5 vocab + 2 grammar + 1 long passage\n"
        "\n"
        "<b>Adding Words:</b>\n"
        "• Via Telegram: /add كتاب book\n"
        "• Via Claude Desktop: Drop an image, Claude extracts + adds words",
        parse_mode="HTML",
    )
