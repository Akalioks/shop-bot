"""Fixed texts the bot sends."""
from html import escape

from .db import Order
from .pricing import euros

STATUS = {
    "new": "🆕 New",
    "paid": "💳 Paid",
    "shipped": "📦 Shipped",
    "done": "✅ Delivered",
    "cancelled": "❌ Cancelled",
}


def welcome(name: str, shop: str, demo: bool, can_open: bool) -> str:
    text = (f"👋 Hi, {escape(name)}! Welcome to <b>{escape(shop)}</b> — Scandinavian home goods.\n\n"
            "Browse the catalog, add items to the cart and check out without leaving Telegram.")
    if not can_open:
        text += "\n\n⚠️ <i>The shop page needs an HTTPS address (WEBAPP_URL) — it isn't configured yet.</i>"
    if demo:
        text += ("\n\n🧪 <i>Demo shop: nothing is really sold. Card payments run in test mode — "
                 "use the card 4242 4242 4242 4242, any future date and any CVC. "
                 "Send /admin to see the owner's side.</i>")
    return text


def order_card(o: Order, for_owner: bool) -> str:
    lines = [f"{i.emoji} {escape(i.name)} × {i.qty} — {euros(i.price * i.qty)}" for i in o.items]
    delivery = f"{escape(o.delivery_name)} — {euros(o.delivery_price) if o.delivery_price else 'free'}"
    pay = "💳 card (paid)" if o.status != "new" and o.payment == "card" else (
        "💳 card — waiting for payment" if o.payment == "card" else "💶 on pickup / delivery")
    text = (f"<b>Order #{o.id}</b> · {STATUS.get(o.status, o.status)}\n\n" + "\n".join(lines) +
            f"\n🚚 {delivery}\n<b>Total: {euros(o.total)}</b> · {pay}")
    if for_owner:
        uname = f" · @{escape(o.username)}" if o.username else ""
        text += f"\n\n👤 {escape(o.name)} · {escape(o.phone)}{uname}"
        if o.address:
            text += f"\n📍 {escape(o.address)}"
        if o.comment:
            text += f"\n💬 {escape(o.comment)}"
        text += f"\n🕐 {o.created_at:%d.%m %H:%M}"
    return text


def customer_update(o: Order) -> str:
    if o.status == "shipped":
        what = "is ready for pickup at Telliskivi 60 🏬" if o.delivery_id == "pickup" else "is on its way 📦"
        return f"Good news! Your order #{o.id} {what}"
    if o.status == "done":
        return f"✅ Order #{o.id} is delivered. Thank you for shopping with us!"
    if o.status == "cancelled":
        refund = " The payment will be refunded within 5 working days." if o.payment == "card" and o.paid_at else ""
        return f"❌ Your order #{o.id} was cancelled.{refund} Questions? Just reply here."
    return f"Order #{o.id}: {STATUS.get(o.status, o.status)}"
