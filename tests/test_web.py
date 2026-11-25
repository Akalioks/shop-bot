"""The Mini App's server API, called the way the real page calls it."""
from aiogram.methods import CreateInvoiceLink

from bot import notify
from tests.conftest import auth

ORDER = {"items": [{"id": 1, "qty": 1}], "delivery": "courier", "payment": "later",
         "name": "Anna", "phone": "+372 5555 1234", "address": "Viru 1, Tallinn", "comment": ""}


async def test_requires_valid_telegram_signature(make_shop):
    shop = await make_shop()
    c = await shop.client()
    assert (await c.get("/api/bootstrap")).status == 401
    assert (await c.get("/api/bootstrap", headers=auth(1, token="0:other-bot"))).status == 401
    assert (await c.get("/api/bootstrap", headers=auth(1, age_sec=3 * 24 * 3600))).status == 401
    tampered = {"Authorization": auth(1)["Authorization"].replace("Anna", "Eve")}
    assert (await c.get("/api/bootstrap", headers=tampered)).status == 401
    await c.close()


async def test_bootstrap(make_shop):
    shop = await make_shop()
    c = await shop.client()
    data = await (await c.get("/api/bootstrap", headers=auth(1))).json()
    assert data["shop"] == "Nordic Home" and len(data["products"]) == 14 and not data["is_admin"]
    assert data["user"]["first_name"] == "Anna" and data["payments_enabled"] is False
    assert {d["id"] for d in data["deliveries"]} == {"courier", "locker", "pickup"}
    owner = await (await c.get("/api/bootstrap", headers=auth(99))).json()
    assert owner["is_admin"]
    await c.close()


async def test_pay_later_order_and_notifications(make_shop):
    shop = await make_shop()
    c = await shop.client()
    body = {**ORDER, "items": [{"id": 1, "qty": 2, "price": 1}]}  # a fake price from the browser is ignored
    res = await c.post("/api/orders", json=body, headers=auth(1))
    data = await res.json()
    assert res.status == 200, data
    await notify.drain()
    order = await shop.repo.order(data["order_id"])
    assert order.items_total == 2 * 7900 and order.delivery_price == 0 and order.total == 15800  # free over €50
    assert any("Order received" in t for t in shop.session.sent_to(1))
    assert any("Order #1" in t and "+372 5555 1234" in t for t in shop.session.sent_to(99))
    assert any("Demo: this is what the shop owner receives" in t for t in shop.session.sent_to(1))

    mine = await (await c.get("/api/orders", headers=auth(1))).json()
    theirs = await (await c.get("/api/orders", headers=auth(2))).json()
    assert len(mine["orders"]) == 1 and theirs["orders"] == []
    await c.close()


async def test_order_validation_messages(make_shop):
    shop = await make_shop()
    c = await shop.client()
    cases = [
        ({"address": ""}, "address"),
        ({"phone": "call me"}, "phone"),
        ({"name": ""}, "name"),
        ({"items": [{"id": 14, "qty": 1}]}, "out of stock"),  # Terracotta vase
        ({"payment": "card"}, "Card payments are not available"),
    ]
    for change, expected in cases:
        res = await c.post("/api/orders", json={**ORDER, **change}, headers=auth(1))
        assert res.status == 400 and expected in (await res.json())["error"], change
    res = await c.post("/api/orders", json={**ORDER, "delivery": "pickup", "address": ""}, headers=auth(1))
    assert res.status == 200  # no address needed for pickup
    res = await c.post("/api/orders", data="not json", headers=auth(1))
    assert res.status == 400
    await c.close()


async def test_card_order_creates_invoice(make_shop):
    shop = await make_shop(payment_provider_token="TEST:stripe")
    c = await shop.client()
    res = await c.post("/api/orders", json={**ORDER, "payment": "card", "items": [{"id": 6, "qty": 2}]}, headers=auth(1))
    data = await res.json()
    assert data["invoice_url"] == "https://t.me/$test_invoice"
    inv = shop.session.of(CreateInvoiceLink)[-1]
    assert inv.payload == f"order:{data['order_id']}" and inv.currency == "EUR"
    assert sum(p.amount for p in inv.prices) == data["total"] == 2 * 1490 + 490
    assert shop.session.sent_to(99) == []  # owner is told only after the payment succeeds
    await c.close()


async def test_invoice_failure_cancels_order(make_shop):
    shop = await make_shop(payment_provider_token="TEST:stripe")
    shop.session.fail_invoice = True
    c = await shop.client()
    res = await c.post("/api/orders", json={**ORDER, "payment": "card"}, headers=auth(1))
    assert res.status == 502
    assert (await shop.repo.order(1)).status == "cancelled"
    await c.close()


async def test_admin_edits_products(make_shop):
    shop = await make_shop()
    c = await shop.client()
    res = await c.patch("/api/admin/products/1", json={"price": 6900, "in_stock": False}, headers=auth(2))
    assert res.status == 403 and "Demo" in (await res.json())["error"]
    res = await c.patch("/api/admin/products/1", json={"price": 6900, "in_stock": False}, headers=auth(99))
    assert res.status == 200 and (await res.json())["product"]["price"] == 6900
    assert (await c.patch("/api/admin/products/1", json={"price": -5}, headers=auth(99))).status == 400
    assert (await c.patch("/api/admin/products/1", json={"price": True}, headers=auth(99))).status == 400
    assert (await c.patch("/api/admin/products/999", json={"price": 100}, headers=auth(99))).status == 404
    res = await c.post("/api/orders", json=ORDER, headers=auth(1))  # product 1 is now out of stock
    assert res.status == 400
    await c.close()


async def test_dev_mode_and_static_page(make_shop):
    shop = await make_shop(dev_mode=True)
    c = await shop.client()
    assert (await c.get("/api/bootstrap")).status == 200  # localhost without Telegram, DEV_MODE only
    page = await c.get("/app/")
    assert page.status == 200 and "telegram-web-app.js" in await page.text()
    assert (await c.get("/app/app.js")).status == 200
    await c.close()
