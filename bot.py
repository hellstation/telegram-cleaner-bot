"""
Telegram bot entry point.
"""

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from prometheus_client import generate_latest

from handlers import router
from metrics import registry

# Load environment
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))

if not TOKEN:
    raise ValueError("BOT_TOKEN not found in .env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def metrics_handler(request):
    """Handler for /metrics endpoint."""
    return web.Response(text=generate_latest(registry).decode('utf-8'), content_type='text/plain', charset='utf-8')


async def web_server():
    """Run the metrics web server."""
    app = web.Application()
    app.router.add_get('/metrics', metrics_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', METRICS_PORT)
    await site.start()
    logger.info(f"Metrics server started on port {METRICS_PORT}")
    # Keep the server running
    await asyncio.Future()


async def main() -> None:
    """Main bot function."""
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Start both bot and metrics server
    await asyncio.gather(
        dp.start_polling(bot),
        web_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot failed: {e}")
        raise
