"""Settings are read from the .env file (see .env.example)."""
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _ids(raw: str) -> frozenset[int]:
    return frozenset(int(x) for x in raw.replace(" ", "").split(",") if x)


def _bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    demo_mode: bool
    tz: ZoneInfo
    database_url: str
    shop_name: str
    webapp_url: str              # public HTTPS address of the Mini App, e.g. https://shop.example.com/app/
    host: str
    port: int
    payment_provider_token: str  # from @BotFather → Payments (e.g. Stripe TEST). Empty = pay on pickup/delivery
    currency: str
    dev_mode: bool               # local testing in a normal browser without Telegram. NEVER on a real server
    dev_user_id: int

    def now(self) -> datetime:
        return datetime.now(self.tz).replace(tzinfo=None)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    @property
    def payments_enabled(self) -> bool:
        return bool(self.payment_provider_token)

    @property
    def webapp_is_https(self) -> bool:
        return self.webapp_url.startswith("https://")


def load_config(**overrides) -> Config:
    load_dotenv()
    env = os.getenv
    values: dict[str, Any] = dict(
        bot_token=env("BOT_TOKEN", ""),
        admin_ids=_ids(env("ADMIN_IDS", "")),
        demo_mode=_bool(env("DEMO_MODE", "true")),
        tz=ZoneInfo(env("TIMEZONE", "Europe/Tallinn")),
        database_url=env("DATABASE_URL", "sqlite+aiosqlite:///shop.db"),
        shop_name=env("SHOP_NAME", "Nordic Home"),
        webapp_url=env("WEBAPP_URL", "http://localhost:8080/app/"),
        host=env("HOST", "0.0.0.0"),
        port=int(env("PORT", "8080")),
        payment_provider_token=env("PAYMENT_PROVIDER_TOKEN", ""),
        currency=env("CURRENCY", "EUR"),
        dev_mode=_bool(env("DEV_MODE", "false")),
        dev_user_id=int(env("DEV_USER_ID", "1")),
    )
    values.update(overrides)
    return Config(**values)
