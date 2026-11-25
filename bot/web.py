"""The web part: serves the Mini App page and its JSON API.

Every API request carries Telegram's signed initData ("Authorization: tma <initData>").
The server checks the signature with the bot token, so nobody can pretend to be another user."""
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import LabeledPrice
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from . import notify
from .config import Config
from .pricing import OrderError, euros, quote
from .repo import Repo

log = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
INIT_DATA_MAX_AGE = timedelta(hours=24)
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{5,20}$")

CFG = web.AppKey("cfg", Config)
REPO = web.AppKey("repo", Repo)
BOT = web.AppKey("bot", Bot)


class Viewer:
    def __init__(self, user_id: int, username: str | None, first_name: str):
        self.id, self.username, self.first_name = user_id, username, first_name


def error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def viewer(request: web.Request) -> Viewer:
    cfg = request.app[CFG]
    header = request.headers.get("Authorization", "")
    if header.startswith("tma ") and len(header) > 4:
        try:
            data = safe_parse_webapp_init_data(cfg.bot_token, header[4:])
        except ValueError:
            raise web.HTTPUnauthorized(text='{"error": "Invalid Telegram signature"}', content_type="application/json")
        auth_date = data.auth_date if data.auth_date.tzinfo else data.auth_date.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - auth_date > INIT_DATA_MAX_AGE or not data.user:
            raise web.HTTPUnauthorized(text='{"error": "Session expired, reopen the shop"}', content_type="application/json")
        return Viewer(data.user.id, data.user.username, data.user.first_name)
    if cfg.dev_mode and request.remote in ("127.0.0.1", "::1"):
        return Viewer(cfg.dev_user_id, "dev", "Developer")  # local browser testing only
    raise web.HTTPUnauthorized(text='{"error": "Open the shop from Telegram"}', content_type="application/json")


def product_json(p) -> dict:
    return {"id": p.id, "category": p.category, "name": p.name, "description": p.description,
            "emoji": p.emoji, "color": p.color, "price": p.price, "in_stock": p.in_stock}


def order_json(o) -> dict:
    return {"id": o.id, "status": o.status, "payment": o.payment, "total": o.total,
            "created_at": o.created_at.strftime("%d.%m.%Y %H:%M"), "delivery": o.delivery_name,
            "items": [{"name": i.name, "emoji": i.emoji, "qty": i.qty, "price": i.price} for i in o.items]}


async def bootstrap(request: web.Request) -> web.Response:
    v, cfg, repo = viewer(request), request.app[CFG], request.app[REPO]
    return web.json_response({
        "shop": cfg.shop_name,
        "currency": cfg.currency,
        "user": {"first_name": v.first_name},
        "is_admin": cfg.is_admin(v.id),
        "demo": cfg.demo_mode,
        "payments_enabled": cfg.payments_enabled,
        "categories": repo.categories,
        "deliveries": [d.__dict__ for d in repo.deliveries.values()],
        "products": [product_json(p) for p in await repo.products()],
    })


async def my_orders(request: web.Request) -> web.Response:
    v = viewer(request)
    return web.json_response({"orders": [order_json(o) for o in await request.app[REPO].user_orders(v.id)]})


def _field(body: dict, key: str, max_len: int, required: bool = True) -> str:
    value = str(body.get(key) or "").strip()
    if required and not value:
        raise OrderError({"name": "Please enter your name.", "phone": "Please enter your phone number.",
                          "address": "Please enter the delivery address."}.get(key, f"{key} is required."))
    if len(value) > max_len:
        raise OrderError(f"{key.capitalize()} is too long.")
    return value


async def place_order(request: web.Request) -> web.Response:
    v = viewer(request)
    cfg, repo, bot = request.app[CFG], request.app[REPO], request.app[BOT]
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return error("Invalid request.")
    try:
        q = quote(body.get("items"), await repo.products_by_id(), repo.deliveries, str(body.get("delivery", "")))
        name = _field(body, "name", 80)
        phone = _field(body, "phone", 32)
        if not PHONE_RE.match(phone):
            raise OrderError("Please enter a valid phone number.")
        address = _field(body, "address", 200, required=q.delivery.id != "pickup")
        comment = _field(body, "comment", 300, required=False)
        payment = "card" if body.get("payment") == "card" else "later"
        if payment == "card" and not cfg.payments_enabled:
            raise OrderError("Card payments are not available — choose pay on pickup / delivery.")
    except OrderError as e:
        return error(str(e))

    order = await repo.create_order(v.id, v.username, q, payment, name, phone, address, comment)
    if payment == "later":
        notify.in_background(notify.order_placed(bot, cfg, order))
        return web.json_response({"order_id": order.id, "total": order.total})

    prices = [LabeledPrice(label=f"{l.name} × {l.qty}", amount=l.price * l.qty) for l in q.lines]
    if q.delivery_price:
        prices.append(LabeledPrice(label=q.delivery.name, amount=q.delivery_price))
    summary = ", ".join(f"{l.name} × {l.qty}" for l in q.lines)
    try:
        url = await bot.create_invoice_link(
            title=f"{cfg.shop_name} · order #{order.id}"[:32],
            description=(summary if len(summary) <= 255 else summary[:252] + "…"),
            payload=f"order:{order.id}",
            currency=cfg.currency,
            prices=prices,
            provider_token=cfg.payment_provider_token,
        )
    except TelegramAPIError as e:
        log.error("Could not create invoice for order %s: %s", order.id, e)
        await repo.set_status(order.id, "cancelled")
        return error("Payment is temporarily unavailable. Please choose pay on pickup / delivery.", 502)
    return web.json_response({"order_id": order.id, "total": order.total, "invoice_url": url})


async def update_product(request: web.Request) -> web.Response:
    v, cfg, repo = viewer(request), request.app[CFG], request.app[REPO]
    if not cfg.is_admin(v.id):
        return error("Demo mode: the catalog is read-only." if cfg.demo_mode else "Not allowed.", 403)
    try:
        product_id = int(request.match_info["id"])
        body = await request.json()
        price = body.get("price")
        in_stock = body.get("in_stock")
        if price is not None and (not isinstance(price, int) or isinstance(price, bool) or not 1 <= price <= 10_000_000):
            return error("Price must be between €0.01 and €100,000.")
        if in_stock is not None and not isinstance(in_stock, bool):
            return error("Invalid stock value.")
    except (ValueError, AttributeError):
        return error("Invalid request.")
    p = await repo.update_product(product_id, price, in_stock)
    if p is None:
        return error("Product not found.", 404)
    log.info("Product %s updated by %s: price=%s in_stock=%s", p.id, v.id, euros(p.price), p.in_stock)
    return web.json_response({"product": product_json(p)})


async def root(request: web.Request) -> web.Response:
    raise web.HTTPFound("/app/")


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@web.middleware
async def security_headers(request: web.Request, handler):
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


def create_web_app(cfg: Config, repo: Repo, bot: Bot) -> web.Application:
    app = web.Application(middlewares=[security_headers], client_max_size=64 * 1024)
    app[CFG], app[REPO], app[BOT] = cfg, repo, bot
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_get("/api/bootstrap", bootstrap)
    app.router.add_get("/api/orders", my_orders)
    app.router.add_post("/api/orders", place_order)
    app.router.add_patch("/api/admin/products/{id}", update_product)
    app.router.add_get("/app/", index)
    app.router.add_static("/app/", WEBAPP_DIR)
    return app
