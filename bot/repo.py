"""All database queries live here."""
import json
from datetime import datetime, time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .config import Config
from .db import Base, Order, OrderItem, Product
from .pricing import Delivery, Quote

CATALOG_FILE = Path(__file__).resolve().parent.parent / "catalog.json"


class Repo:
    def __init__(self, engine: AsyncEngine, cfg: Config, catalog: dict):
        self.engine = engine
        self.cfg = cfg
        self.session = async_sessionmaker(engine, expire_on_commit=False)
        self.categories: list[dict] = catalog["categories"]
        self.deliveries: dict[str, Delivery] = {d["id"]: Delivery(**d) for d in catalog["delivery"]}
        self._seed_products = catalog["products"]

    @classmethod
    async def create(cls, cfg: Config, catalog_file: Path = CATALOG_FILE) -> "Repo":
        engine = create_async_engine(cfg.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        repo = cls(engine, cfg, json.loads(catalog_file.read_text(encoding="utf-8")))
        await repo._seed()
        return repo

    async def _seed(self) -> None:
        async with self.session() as s:
            if await s.scalar(select(func.count(Product.id))):
                return
            s.add_all(Product(**p) for p in self._seed_products)
            await s.commit()

    async def close(self) -> None:
        await self.engine.dispose()

    # ---------- products ----------
    async def products(self) -> list[Product]:
        async with self.session() as s:
            return list((await s.scalars(select(Product).order_by(Product.id))).all())

    async def products_by_id(self) -> dict[int, Product]:
        return {p.id: p for p in await self.products()}

    async def update_product(self, product_id: int, price: int | None, in_stock: bool | None) -> Product | None:
        async with self.session() as s:
            p = await s.get(Product, product_id)
            if p is None:
                return None
            if price is not None:
                p.price = price
            if in_stock is not None:
                p.in_stock = in_stock
            await s.commit()
            return p

    # ---------- orders ----------
    async def create_order(self, user_id: int, username: str | None, q: Quote, payment: str,
                           name: str, phone: str, address: str, comment: str) -> Order:
        async with self.session() as s:
            order = Order(
                user_id=user_id, username=username, payment=payment,
                delivery_id=q.delivery.id, delivery_name=q.delivery.name, delivery_price=q.delivery_price,
                items_total=q.items_total, total=q.total, name=name, phone=phone, address=address,
                comment=comment, created_at=self.cfg.now(),
                items=[OrderItem(product_id=l.product_id, name=l.name, emoji=l.emoji, price=l.price, qty=l.qty)
                       for l in q.lines],
            )
            s.add(order)
            await s.commit()
            return order

    async def order(self, order_id: int) -> Order | None:
        async with self.session() as s:
            return await s.get(Order, order_id)

    async def user_orders(self, user_id: int, limit: int = 20) -> list[Order]:
        async with self.session() as s:
            q = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
            return list((await s.scalars(q)).all())

    async def mark_paid(self, order_id: int, charge_id: str) -> Order | None:
        async with self.session() as s:
            o = await s.get(Order, order_id)
            if o is None or o.status != "new":
                return None
            o.status, o.paid_at, o.payment_charge_id = "paid", self.cfg.now(), charge_id
            await s.commit()
            return o

    async def set_status(self, order_id: int, status: str, only_user_id: int | None = None) -> Order | None:
        async with self.session() as s:
            o = await s.get(Order, order_id)
            if o is None or (only_user_id and o.user_id != only_user_id):
                return None
            o.status = status
            await s.commit()
            return o

    async def recent_orders(self, statuses: tuple[str, ...], user_id: int | None = None, limit: int = 15) -> list[Order]:
        q = select(Order).where(Order.status.in_(statuses)).order_by(Order.id.desc()).limit(limit)
        if user_id:
            q = q.where(Order.user_id == user_id)
        async with self.session() as s:
            return list((await s.scalars(q)).all())

    async def sales_since(self, since: datetime, user_id: int | None = None) -> tuple[int, int]:
        """(number of orders, revenue in cents), not counting cancelled ones."""
        q = select(func.count(Order.id), func.sum(Order.total)).where(
            Order.created_at >= since, Order.status != "cancelled")
        if user_id:
            q = q.where(Order.user_id == user_id)
        async with self.session() as s:
            n, total = (await s.execute(q)).one()
        return n or 0, total or 0

    def day_start(self) -> datetime:
        return datetime.combine(self.cfg.now().date(), time.min)
