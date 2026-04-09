import asyncio
import logging
from telegram import Update
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


def _build_app():
    """Build and configure the Telegram Application."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app


def _run_polling(app):
    """Run in polling mode (local dev / VM hosting)."""
    logger.info("Starting in polling mode (no RENDER_EXTERNAL_URL set)")
    app.run_polling(allowed_updates=["message", "callback_query"])


def _run_webhook(app):
    """Run in webhook mode with custom Starlette app for extra routes."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
    logger.info(f"Starting in webhook mode on port {PORT}")
    logger.info(f"Webhook URL: {webhook_url}")

    async def health(request):
        return PlainTextResponse("OK")

    async def handle_webhook(request):
        """Process incoming Telegram webhook updates."""
        if WEBHOOK_SECRET:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token != WEBHOOK_SECRET:
                return PlainTextResponse("Unauthorized", status_code=401)

        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.update_queue.put(update)
        return PlainTextResponse("OK")

    async def trigger_review(request, session_type):
        token = request.query_params.get("secret", "")
        if TRIGGER_SECRET and token != TRIGGER_SECRET:
            return PlainTextResponse("Unauthorized", status_code=401)

        class _Ctx:
            bot = app.bot
            bot_data = app.bot_data
        await send_review_session(_Ctx(), session_type=session_type)
        return PlainTextResponse(f"OK: {session_type} review sent")

    async def trigger_morning(request):
        return await trigger_review(request, "morning")

    async def trigger_lunch(request):
        return await trigger_review(request, "lunch")

    async def trigger_dinner(request):
        return await trigger_review(request, "dinner")

    starlette_app = Starlette(
        routes=[
            Route("/health", health),
            Route("/webhook", handle_webhook, methods=["POST"]),
            Route("/trigger/morning", trigger_morning),
            Route("/trigger/lunch", trigger_lunch),
            Route("/trigger/dinner", trigger_dinner),
        ],
    )

    async def run():
        # Initialize the application (connects to Telegram, etc.)
        await app.initialize()
        await app.start()

        # Set the webhook
        await app.bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET or None,
            allowed_updates=["message", "callback_query"],
        )

        # Run uvicorn server
        config = uvicorn.Config(
            starlette_app, host="0.0.0.0", port=PORT, log_level="info"
        )
        server = uvicorn.Server(config)
        try:
            await server.serve()
        finally:
            await app.stop()
            await app.shutdown()

    asyncio.run(run())


def main():
    app = _build_app()

    if RENDER_EXTERNAL_URL:
        _run_webhook(app)
    else:
        _run_polling(app)


if __name__ == "__main__":
    main()
