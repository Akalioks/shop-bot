"""Messages about orders: to the customer and to the shop owners."""
import asyncio
import logging
from collections.abc import Coroutine

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from . import keyboards as kb
from . import texts
from .config import Config
from .db import Order

log = logging.getLogger(__name__)
_pending: set[asyncio.Task] = set()


def in_background(coro: Coroutine) -> None:
    """Sends messages without making the customer's checkout wait for Telegram."""
    task = asyncio.create_task(coro)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    """Waits for background messages to finish (on shutdown, and in tests)."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


async def send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramAPIError as e:
        log.warning("Could not message %s: %s", chat_id, e)
        return False


async def order_placed(bot: Bot, cfg: Config, order: Order) -> None:
    """Confirmation to the customer + the order card with status buttons to the owners."""
    head = "✅ <b>Thank you! Order received.</b>" if order.payment == "later" else "✅ <b>Payment received, thank you!</b>"
    await send(bot, order.user_id, f"{head}\n\n{texts.order_card(order, for_owner=False)}\n\n"
                                   "We'll message you here when it ships.")
    card = "🛒 " + texts.order_card(order, for_owner=True)
    for admin_id in cfg.admin_ids:
        await send(bot, admin_id, card, reply_markup=kb.order_actions(order))
    if cfg.demo_mode and order.user_id not in cfg.admin_ids:
        await send(bot, order.user_id, "👀 <i>Demo: this is what the shop owner receives — try the buttons:</i>\n\n"
                   + card, reply_markup=kb.order_actions(order))
