"""Order validation and totals — pure logic, no database. The server always recalculates prices
from its own catalog; whatever prices the browser sends are ignored."""
from dataclasses import dataclass

MAX_QTY = 20
MAX_LINES = 30


class OrderError(ValueError):
    """A problem the customer can fix; the message is shown in the Mini App."""


@dataclass(frozen=True)
class Delivery:
    id: str
    name: str
    eta: str
    price: int
    free_from: int  # 0 = never free (or already free)

    def cost(self, items_total: int) -> int:
        return 0 if self.free_from and items_total >= self.free_from else self.price


@dataclass(frozen=True)
class Line:
    product_id: int
    name: str
    emoji: str
    price: int
    qty: int


@dataclass(frozen=True)
class Quote:
    lines: list[Line]
    items_total: int
    delivery: Delivery
    delivery_price: int

    @property
    def total(self) -> int:
        return self.items_total + self.delivery_price


def quote(cart: list[dict], products: dict, deliveries: dict[str, Delivery], delivery_id: str) -> Quote:
    """cart: [{"id": product_id, "qty": n}], products: {id: Product}."""
    if not isinstance(cart, list) or not cart:
        raise OrderError("Your cart is empty.")
    if len(cart) > MAX_LINES:
        raise OrderError("Too many different items in one order.")
    merged: dict[int, int] = {}
    for row in cart:
        try:
            pid, qty = int(row["id"]), int(row["qty"])
        except (KeyError, TypeError, ValueError):
            raise OrderError("Invalid cart.") from None
        if qty < 1:
            raise OrderError("Invalid quantity.")
        merged[pid] = merged.get(pid, 0) + qty
    lines = []
    for pid, qty in merged.items():
        p = products.get(pid)
        if p is None:
            raise OrderError("A product in your cart no longer exists. Please refresh.")
        if not p.in_stock:
            raise OrderError(f"Sorry, “{p.name}” is out of stock.")
        if qty > MAX_QTY:
            raise OrderError(f"You can order at most {MAX_QTY} of “{p.name}”.")
        lines.append(Line(p.id, p.name, p.emoji, p.price, qty))
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise OrderError("Please choose a delivery method.")
    items_total = sum(l.price * l.qty for l in lines)
    return Quote(lines, items_total, delivery, delivery.cost(items_total))


def euros(cents: int) -> str:
    return f"€{cents // 100}.{cents % 100:02d}"
