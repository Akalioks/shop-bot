"""Run with:  python -m bot   — starts the Telegram bot and the web server for the Mini App together."""
import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from aiohttp import web

from . import notify
from .app import build_dispatcher
from .config import load_config
from .repo import Repo
from .web import create_web_app

log = logging.getLogger("shop")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    cfg = load_config()
    if not cfg.bot_token:
        sys.exit("BOT_TOKEN is empty. Copy .env.example to .env and paste the token from @BotFather.")
    if cfg.dev_mode:
        log.warning("DEV_MODE is on: the API trusts requests from localhost without Telegram. Never use it on a server!")

    repo = await Repo.create(cfg)
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands([
        BotCommand(command="start", description="Open the shop"),
        BotCommand(command="orders", description="My orders"),
    ])
    if cfg.webapp_is_https:  # the blue menu button next to the message field opens the shop
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Shop", web_app=WebAppInfo(url=cfg.webapp_url)))
    else:
        log.warning("WEBAPP_URL is not HTTPS (%s) — Telegram can't open the shop yet. "
                    "Open it in a browser with DEV_MODE=true for local testing.", cfg.webapp_url)

    runner = web.AppRunner(create_web_app(cfg, repo, bot))
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    log.info("Shop web server on http://%s:%s/app/", "localhost" if cfg.host == "0.0.0.0" else cfg.host, cfg.port)

    try:
        await build_dispatcher(cfg, repo).start_polling(bot)
    finally:
        await runner.cleanup()
        await notify.drain()
        await repo.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
