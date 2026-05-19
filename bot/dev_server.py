"""Local dev runner for the Mini App JSON API.

Boots only the Starlette /api/* routes — no Telegram webhook setup, no
polling. Pair with `DEV_BYPASS_AUTH=1` and a `.env` so the webapp's
`npm run dev` has a backend to talk to.

    DEV_BYPASS_AUTH=1 python -m bot.dev_server
"""
import logging

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from bot import api
from bot.config import DEV_BYPASS_AUTH, PORT, WEB_APP_ORIGIN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def health(request):
    return PlainTextResponse("OK")


def build_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health),
            Route("/api/session", api.get_session, methods=["GET"]),
            Route("/api/session/result", api.post_result, methods=["POST"]),
            Route("/api/lookup", api.lookup_word, methods=["GET"]),
            Route("/api/raw_words", api.post_raw_word, methods=["POST"]),
            Route("/api/raw-passages", api.post_raw_passage, methods=["POST"]),
            Route("/api/passage/shown", api.post_passage_shown, methods=["POST"]),
            Route("/api/stats", api.get_stats, methods=["GET"]),
            Route("/api/cowork/vocabulary", api.cowork_post_vocabulary, methods=["POST"]),
            Route("/api/cowork/passages", api.cowork_post_passages, methods=["POST"]),
            Route("/api/cowork/vocab-for-passage", api.cowork_get_vocab_for_passage, methods=["GET"]),
            Route("/api/cowork/raw-passages", api.cowork_get_raw_passages, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[WEB_APP_ORIGIN] if WEB_APP_ORIGIN != "*" else ["*"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "X-Telegram-Init-Data", "X-Cowork-Token"],
                max_age=600,
            ),
        ],
    )


if __name__ == "__main__":
    if not DEV_BYPASS_AUTH:
        logger.warning(
            "DEV_BYPASS_AUTH is not set — /api/* will reject browser requests "
            "with 401. Run with DEV_BYPASS_AUTH=1 for local webapp testing."
        )
    logger.info("Starting dev API server on port %s", PORT)
    uvicorn.run(build_app(), host="127.0.0.1", port=PORT, log_level="info")
