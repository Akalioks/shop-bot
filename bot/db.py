"""Database tables. SQLite by default, PostgreSQL works by changing DATABASE_URL. Money is stored in cents."""
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    emoji: Mapped[str] = mapped_column(String(8), default="📦")
    color: Mapped[str] = mapped_column(String(9), default="#CCCCCC")
    price: Mapped[int]  # cents
    in_stock: Mapped[bool] = mapped_column(default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    # new → paid (card) → shipped → done; or cancelled. Pay-later orders go new → shipped → done.
    status: Mapped[str] = mapped_column(String(16), default="new")
    payment: Mapped[str] = mapped_column(String(16))  # card | later
    delivery_id: Mapped[str] = mapped_column(String(16))
    delivery_name: Mapped[str] = mapped_column(String(80))
    delivery_price: Mapped[int]
    items_total: Mapped[int]
    total: Mapped[int]
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(String(200), default="")
    comment: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime]
    paid_at: Mapped[datetime | None]
    payment_charge_id: Mapped[str | None] = mapped_column(String(128))

    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int]
    name: Mapped[str] = mapped_column(String(80))  # copied, so old orders stay correct if the product changes
    emoji: Mapped[str] = mapped_column(String(8))
    price: Mapped[int]
    qty: Mapped[int]
