"""Local preview of the shop page in a normal browser — no Telegram, no bot token needed.

    .venv\\Scripts\\python dev_server.py      then open  http://localhost:8080/app/

You are signed in as a fake owner (so the Admin tab is editable). Messages to Telegram are skipped.
Uses its own database file (dev.db), separate from the real shop.db."""
import asyncio
import logging

from aiogram import Bot
from aiohttp import web

from bot import notify
from bot.config import load_config
from bot.repo import Repo
from bot.web import create_web_app

DEV_USER = 1


async def _log_only(bot, chat_id, text, **kwargs) -> bool:
    logging.getLogger("preview").info("Telegram message to %s (skipped in preview):\n%s", chat_id, text)
    return True

notify.send = _log_only  # no real bot here, so just print what would be sent


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(bot_token="0:dev", dev_mode=True, dev_user_id=DEV_USER, admin_ids=frozenset({DEV_USER}),
                      database_url="sqlite+aiosqlite:///dev.db", host="127.0.0.1", payment_provider_token="")
    repo = await Repo.create(cfg)
    bot = Bot(cfg.bot_token)
    runner = web.AppRunner(create_web_app(cfg, repo, bot))
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    print(f"\n  Shop preview: http://localhost:{cfg.port}/app/   (Ctrl+C to stop)\n")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
