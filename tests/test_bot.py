"""Chat side: /start, card payment confirmation, order status buttons."""
from datetime import datetime

from aiogram.methods import AnswerPreCheckoutQuery, SendMessage
from aiogram.types import (CallbackQuery, Chat, Message, PreCheckoutQuery, SuccessfulPayment,
                           User as TgUser)

from bot import notify
from bot.keyboards import OrderCb
from tests.test_web import ORDER

ANNA = TgUser(id=1, is_bot=False, first_name="Anna", username="anna")
OWNER = TgUser(id=99, is_bot=False, first_name="Owner")
BOB = TgUser(id=2, is_bot=False, first_name="Bob")


def msg(user, **kw) -> Message:
    return Message(message_id=1, date=datetime.now(), chat=Chat(id=user.id, type="private"), from_user=user, **kw)


async def place(shop, user_id=1, **change):
    from tests.conftest import auth
    c = await shop.client()
    data = await (await c.post("/api/orders", json={**ORDER, **change}, headers=auth(user_id))).json()
    await c.close()
    await notify.drain()
    return await shop.repo.order(data["order_id"])


async def test_start_shows_shop_button(make_shop):
    shop = await make_shop()
    await shop.feed(message=msg(ANNA, text="/start"))
    sent = shop.session.of(SendMessage)[-1]
    assert "Welcome to <b>Nordic Home</b>" in sent.text
    assert sent.reply_markup.inline_keyboard[0][0].web_app.url == "https://shop.example.com/app/"

    local = await make_shop(webapp_url="http://localhost:8080/app/")
    await local.feed(message=msg(ANNA, text="/start"))
    sent = local.session.of(SendMessage)[-1]
    assert sent.reply_markup is None and "needs an HTTPS address" in sent.text


async def test_card_payment_flow(make_shop):
    shop = await make_shop(payment_provider_token="TEST:stripe")
    order = await place(shop, payment="card")

    async def precheck(user, amount, payload):
        await shop.feed(pre_checkout_query=PreCheckoutQuery(
            id="q", from_user=user, currency="EUR", total_amount=amount, invoice_payload=payload))
        return shop.session.of(AnswerPreCheckoutQuery)[-1]

    assert not (await precheck(BOB, order.total, f"order:{order.id}")).ok  # someone else's order
    assert not (await precheck(ANNA, order.total + 1, f"order:{order.id}")).ok  # wrong amount
    assert not (await precheck(ANNA, order.total, "order:999")).ok
    assert (await precheck(ANNA, order.total, f"order:{order.id}")).ok

    paid = SuccessfulPayment(currency="EUR", total_amount=order.total, invoice_payload=f"order:{order.id}",
                             telegram_payment_charge_id="tg_1", provider_payment_charge_id="pi_1")
    await shop.feed(message=msg(ANNA, successful_payment=paid))
    order = await shop.repo.order(order.id)
    assert order.status == "paid" and order.payment_charge_id == "tg_1"
    assert any("Payment received" in t for t in shop.session.sent_to(1))
    assert any("💳 Paid" in t for t in shop.session.sent_to(99))

    await shop.feed(message=msg(ANNA, successful_payment=paid))  # duplicate update → no second notification
    assert sum("Payment received" in t for t in shop.session.sent_to(1)) == 1
    assert not (await precheck(ANNA, order.total, f"order:{order.id}")).ok  # can't pay twice


async def test_owner_moves_order_through_statuses(make_shop):
    shop = await make_shop()
    order = await place(shop, delivery="pickup", address="")

    async def press(user, action):
        cq = CallbackQuery(id="c", from_user=user, chat_instance="ci", data=OrderCb(id=order.id, action=action).pack(),
                           message=msg(user, text="card"))
        await shop.feed(callback_query=cq)

    await press(OWNER, "done")  # can't deliver before shipping
    assert (await shop.repo.order(order.id)).status == "new"
    await press(OWNER, "shipped")
    assert any("ready for pickup" in t for t in shop.session.sent_to(1))
    await press(OWNER, "done")
    assert (await shop.repo.order(order.id)).status == "done"
    assert any("is delivered" in t for t in shop.session.sent_to(1))

    await press(BOB, "cancelled")  # demo visitor can't touch other people's orders
    assert (await shop.repo.order(order.id)).status == "done"


async def test_admin_summary_scoped(make_shop):
    shop = await make_shop()
    await place(shop, user_id=1)
    await place(shop, user_id=2)
    await shop.feed(message=msg(OWNER, text="/admin"))
    assert "Open orders (2)" in shop.session.sent_to(99)[-1]
    await shop.feed(message=msg(BOB, text="/admin"))
    assert "Open orders (1)" in shop.session.sent_to(2)[-1] and "Demo mode" in shop.session.sent_to(2)[-1]

    closed = await make_shop(demo_mode=False)
    await closed.feed(message=msg(BOB, text="/admin"))
    assert closed.session.sent_to(2) == []
