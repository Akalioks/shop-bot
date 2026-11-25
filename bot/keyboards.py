"""Buttons and the data they carry."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import Order


class OrderCb(CallbackData, prefix="ord"):
    id: int
    action: str  # view | shipped | done | cancelled


def open_shop(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Open the shop", web_app=WebAppInfo(url=url))
    return kb.as_markup()


def order_actions(o: Order) -> InlineKeyboardMarkup | None:
    kb = InlineKeyboardBuilder()
    if o.status in ("new", "paid"):
        kb.button(text="📦 Mark shipped", callback_data=OrderCb(id=o.id, action="shipped"))
        kb.button(text="❌ Cancel", callback_data=OrderCb(id=o.id, action="cancelled"))
    elif o.status == "shipped":
        kb.button(text="✅ Mark delivered", callback_data=OrderCb(id=o.id, action="done"))
    else:
        return None
    kb.adjust(2)
    return kb.as_markup()


def orders_list(orders: list[Order]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for o in orders:
        kb.button(text=f"#{o.id} · {o.name[:18]} · €{o.total / 100:.2f} · {o.status}",
                  callback_data=OrderCb(id=o.id, action="view"))
    kb.adjust(1)
    return kb.as_markup()
