from types import SimpleNamespace as P

import pytest

from bot.pricing import Delivery, OrderError, euros, quote

PRODUCTS = {1: P(id=1, name="Mug", emoji="☕", price=1490, in_stock=True),
            2: P(id=2, name="Lamp", emoji="💡", price=4000, in_stock=True),
            3: P(id=3, name="Vase", emoji="🏺", price=3400, in_stock=False)}
DELIVERIES = {"courier": Delivery("courier", "Courier", "1–2 days", 490, 5000),
              "pickup": Delivery("pickup", "Pickup", "2 h", 0, 0)}


def test_totals_and_delivery():
    q = quote([{"id": 1, "qty": 2}], PRODUCTS, DELIVERIES, "courier")
    assert q.items_total == 2980 and q.delivery_price == 490 and q.total == 3470


def test_free_delivery_threshold():
    q = quote([{"id": 2, "qty": 1}, {"id": 1, "qty": 1}], PRODUCTS, DELIVERIES, "courier")
    assert q.items_total == 5490 and q.delivery_price == 0


def test_duplicate_lines_are_merged():
    q = quote([{"id": 1, "qty": 1}, {"id": 1, "qty": 2}], PRODUCTS, DELIVERIES, "pickup")
    assert len(q.lines) == 1 and q.lines[0].qty == 3


def test_client_prices_are_ignored():
    q = quote([{"id": 1, "qty": 1, "price": 1}], PRODUCTS, DELIVERIES, "pickup")
    assert q.total == 1490


@pytest.mark.parametrize("cart, delivery, msg", [
    ([], "pickup", "empty"),
    ([{"id": 99, "qty": 1}], "pickup", "no longer exists"),
    ([{"id": 3, "qty": 1}], "pickup", "out of stock"),
    ([{"id": 1, "qty": 0}], "pickup", "quantity"),
    ([{"id": 1, "qty": 21}], "pickup", "at most"),
    ([{"id": "x", "qty": 1}], "pickup", "Invalid cart"),
    ([{"id": 1, "qty": 1}], "teleport", "delivery"),
])
def test_rejects_bad_orders(cart, delivery, msg):
    with pytest.raises(OrderError, match=msg):
        quote(cart, PRODUCTS, DELIVERIES, delivery)


def test_euros():
    assert euros(1490) == "€14.90" and euros(5) == "€0.05"
