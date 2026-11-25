"""Customer side in the chat: /start with the shop button, /orders, and card payments."""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, PreCheckoutQuery

from .. import keyboards as kb
from .. import notify, texts
from ..config import Config
from ..repo import Repo

router = Router(name="shop")
log = logging.getLogger(__name__)


@router.message(CommandStart())
@router.message(Command("shop"))
async def start(message: Message, cfg: Config) -> None:
    name = message.from_user.first_name if message.from_user else "there"
    markup = kb.open_shop(cfg.webapp_url) if cfg.webapp_is_https else None
    await message.answer(texts.welcome(name, cfg.shop_name, cfg.demo_mode, cfg.webapp_is_https), reply_markup=markup)


@router.message(Command("orders"))
async def my_orders(message: Message, repo: Repo) -> None:
    if not message.from_user:
        return
    orders = await repo.user_orders(message.from_user.id, limit=5)
    if not orders:
        await message.answer("You have no orders yet.")
        return
    await message.answer("\n\n".join(texts.order_card(o, for_owner=False) for o in orders))


# ---------- card payments (Telegram Payments) ----------
@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, repo: Repo, cfg: Config) -> None:
    """Telegram asks 'may I charge this?' right before taking the money — we double-check the order."""
    order_id = int(query.invoice_payload.split(":", 1)[1]) if query.invoice_payload.startswith("order:") else 0
    order = await repo.order(order_id)
    if order is None or order.user_id != query.from_user.id:
        await query.answer(ok=False, error_message="Order not found. Please place the order again.")
    elif order.status != "new":
        await query.answer(ok=False, error_message="This order is already paid or cancelled.")
    elif order.total != query.total_amount or query.currency != cfg.currency:
        await query.answer(ok=False, error_message="The order total has changed. Please place the order again.")
    else:
        await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, repo: Repo, cfg: Config, bot: Bot) -> None:
    payment = message.successful_payment
    assert payment is not None
    order_id = int(payment.invoice_payload.split(":", 1)[1])
    order = await repo.mark_paid(order_id, payment.telegram_payment_charge_id)
    if order is None:
        log.error("Payment for unknown or already-paid order %s (charge %s)", order_id, payment.telegram_payment_charge_id)
        return
    await notify.order_placed(bot, cfg, order)
