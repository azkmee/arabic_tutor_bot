from telegram.ext import ContextTypes
from bot.handlers.review import send_webapp_notification


async def morning_review(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: Morning review at 9AM SGT."""
    await send_webapp_notification(context, session_type="morning")


async def lunch_review(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: Lunch review at 1PM SGT."""
    await send_webapp_notification(context, session_type="lunch")


async def dinner_review(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: Dinner review at 8PM SGT."""
    await send_webapp_notification(context, session_type="dinner")
