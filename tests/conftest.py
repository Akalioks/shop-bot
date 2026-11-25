"""Test helpers: a fake Telegram API, correctly signed Mini App initData, a ready shop."""
import hashlib
import hmac
import itertools
import json
import time
from datetime import datetime
from urllib.parse import urlencode

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import AnswerPreCheckoutQuery, CreateInvoiceLink, EditMessageText, SendMessage
from aiogram.types import Chat, Message
from aiohttp.test_utils import TestClient, TestServer

from bot.app import build_dispatcher
from bot.config import load_config
from bot.handlers import owner, shop
from bot.repo import Repo
from bot.web import create_web_app

TOKEN = "42:TEST-token"


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.ids = itertools.count(1000)
        self.fail_invoice = False

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=next(self.ids), date=datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        if isinstance(method, EditMessageText):
            return Message(message_id=method.message_id or 0, date=datetime.now(),
                           chat=Chat(id=method.chat_id or 0, type="private"), text=method.text)
        if isinstance(method, CreateInvoiceLink):
            if self.fail_invoice:
                from aiogram.exceptions import TelegramBadRequest
                raise TelegramBadRequest(method=method, message="PAYMENT_PROVIDER_INVALID")
            return "https://t.me/$test_invoice"
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def close(self):
        pass

    def sent_to(self, chat_id) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, (SendMessage, EditMessageText)) and m.chat_id == chat_id]

    def of(self, cls):
        return [m for m in self.calls if isinstance(m, cls)]


def init_data(user_id: int, first_name="Anna", username="anna", token=TOKEN, age_sec=0) -> str:
    """Builds initData exactly the way Telegram signs it."""
    data = {"auth_date": str(int(time.time()) - age_sec), "query_id": "AAH",
            "user": json.dumps({"id": user_id, "first_name": first_name, "username": username}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def auth(user_id: int, **kw) -> dict:
    return {"Authorization": "tma " + init_data(user_id, **kw)}


class Shop:
    def __init__(self, cfg, repo):
        self.cfg, self.repo = cfg, repo
        self.session = FakeSession()
        self.bot = Bot(TOKEN, session=self.session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        for r in (owner.router, shop.router):
            r._parent_router = None  # module-level routers attach once; each test gets a fresh dispatcher
        self.dp = build_dispatcher(cfg, repo)
        self.ids = itertools.count(1)

    async def client(self) -> TestClient:
        c = TestClient(TestServer(create_web_app(self.cfg, self.repo, self.bot)))
        await c.start_server()
        return c

    async def feed(self, **update):
        from aiogram.types import Update
        await self.dp.feed_update(self.bot, Update(update_id=next(self.ids), **update))


@pytest.fixture
async def make_shop(tmp_path):
    made = []

    async def factory(**overrides):
        settings = {"bot_token": TOKEN, "database_url": f"sqlite+aiosqlite:///{tmp_path}/s{len(made)}.db",
                    "admin_ids": frozenset({99}), "demo_mode": True, "payment_provider_token": "",
                    "webapp_url": "https://shop.example.com/app/", "dev_mode": False, **overrides}
        cfg = load_config(**settings)
        s = Shop(cfg, await Repo.create(cfg))
        made.append(s)
        return s

    yield factory
    for s in made:
        await s.repo.close()
