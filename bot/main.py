import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import (
    TELEGRAM_TOKEN, PORT, RENDER_EXTERNAL_URL,
    WEBHOOK_SECRET, TRIGGER_SECRET,
)
from bot.handlers.review import review_command, handle_callback, send_review_session
from bot.handlers.add_words import add_command
from bot.handlers.commands import status_command, help_command

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _trigger_review(request, app, session_type):
    """HTTP handler for cron-triggered review sessions."""
    from starlette.responses import PlainTextResponse

    # Verify trigger secret
    token = request.query_params.get("secret", "")
    if TRIGGER_SECRET and token != TRIGGER_SECRET:
        return PlainTextResponse("Unauthorized", status_code=401)

    # Use a fake context to call send_review_session
    class _Ctx:
        bot = app.bot
        bot_data = app.bot_data
    await send_review_session(_Ctx(), session_type=session_type)
    return PlainTextResponse(f"OK: {session_type} review sent")


async def _health(request):
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("OK")


def _build_starlette_routes(app):
    """Build extra HTTP routes for health check and cron triggers."""
    from starlette.routing import Route

    async def health(request):
        return await _health(request)

    async def trigger_morning(request):
        return await _trigger_review(request, app, "morning")

    async def trigger_lunch(request):
        return await _trigger_review(request, app, "lunch")

    async def trigger_dinner(request):
        return await _trigger_review(request, app, "dinner")

    return [
        Route("/health", health),
        Route("/trigger/morning", trigger_morning),
        Route("/trigger/lunch", trigger_lunch),
        Route("/trigger/dinner", trigger_dinner),
    ]


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

    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"

    if RENDER_EXTERNAL_URL:
        # Webhook mode (for Render / cloud hosting)
        logger.info(f"Starting in webhook mode on port {PORT}")
        logger.info(f"Webhook URL: {webhook_url}")

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET or None,
            allowed_updates=["message", "callback_query"],
            other_routes=_build_starlette_routes(app),
        )
    else:
        # Polling mode (for local dev / VM hosting)
        logger.info("Starting in polling mode (no RENDER_EXTERNAL_URL set)")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
