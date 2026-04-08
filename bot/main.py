import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import TELEGRAM_TOKEN, MORNING_TIME, LUNCH_TIME, DINNER_TIME
from bot.handlers.review import review_command, handle_callback
from bot.handlers.add_words import add_command
from bot.handlers.commands import status_command, help_command
from bot.jobs.scheduled_reviews import morning_review, lunch_review, dinner_review

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))

    # Callback query handler for review buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Scheduled review jobs (3x daily)
    job_queue = app.job_queue
    job_queue.run_daily(morning_review, time=MORNING_TIME, name="morning_review")
    job_queue.run_daily(lunch_review, time=LUNCH_TIME, name="lunch_review")
    job_queue.run_daily(dinner_review, time=DINNER_TIME, name="dinner_review")

    logger.info("Bot started with 3x daily reviews (morning/lunch/dinner)")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
