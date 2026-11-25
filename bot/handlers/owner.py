"""Shop owner side: order status buttons and the /admin summary.

Real owners are ADMIN_IDS. In DEMO_MODE a visitor can manage only their own test orders,
so they can see both sides of the shop."""
from datetime import timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import notify, texts
from ..config import Config
from ..pricing import euros
from ..repo import Repo

router = Router(name="owner")
OPEN = ("new", "paid", "shipped")


def scope(user_id: int, cfg: Config) -> int | None:
    """None = owner sees all orders; a user id = demo visitor sees only their own."""
    return None if cfg.is_admin(user_id) else user_id


def allowed(user_id: int, cfg: Config) -> bool:
    return cfg.is_admin(user_id) or cfg.demo_mode


@router.message(Command("admin"))
async def admin(message: Message, repo: Repo, cfg: Config) -> None:
    if not message.from_user or not allowed(message.from_user.id, cfg):
        return
    who = scope(message.from_user.id, cfg)
    n_today, sum_today = await repo.sales_since(repo.day_start(), who)
    n_week, sum_week = await repo.sales_since(repo.day_start() - timedelta(days=6), who)
    orders = await repo.recent_orders(OPEN, who)
    text = (f"🛠 <b>{cfg.shop_name} · orders</b>\n\n"
            f"<b>Today:</b> {n_today} orders · {euros(sum_today)}\n"
            f"<b>7 days:</b> {n_week} orders · {euros(sum_week)}\n\n"
            + (f"<b>Open orders ({len(orders)}):</b> tap one to manage it." if orders else "No open orders 🎉")
            + "\n\nPrices and stock are edited in the shop's <b>Admin</b> tab.")
    if who is not None:
        text += "\n\n🧪 <i>Demo mode: you see and manage only your own test orders.</i>"
    await message.answer(text, reply_markup=kb.orders_list(orders) if orders else None)


@router.callback_query(kb.OrderCb.filter())
async def order_action(cb: CallbackQuery, callback_data: kb.OrderCb, repo: Repo, cfg: Config, bot: Bot) -> None:
    uid = cb.from_user.id
    if not allowed(uid, cfg):
        await cb.answer("Not allowed.", show_alert=True)
        return
    order = await repo.order(callback_data.id)
    if order is None or (scope(uid, cfg) and order.user_id != uid):
        await cb.answer("Order not found.", show_alert=True)
        return

    if callback_data.action != "view":
        valid = {"shipped": ("new", "paid"), "cancelled": ("new", "paid"), "done": ("shipped",)}
        if order.status not in valid.get(callback_data.action, ()):
            await cb.answer(f"Order is already {texts.STATUS.get(order.status, order.status)}.", show_alert=True)
            return
        order = await repo.set_status(order.id, callback_data.action)
        assert order is not None
        await notify.send(bot, order.user_id, texts.customer_update(order))
        await cb.answer("Updated — the customer was notified.")
    else:
        await cb.answer()

    card = "🛒 " + texts.order_card(order, for_owner=True)
    if callback_data.action == "view" or not isinstance(cb.message, Message):
        await bot.send_message(uid, card, reply_markup=kb.order_actions(order))
    else:
        await cb.message.edit_text(card, reply_markup=kb.order_actions(order))
