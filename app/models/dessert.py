import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import DessertStatus, sql_enum


class Dessert(Base):
    __tablename__ = "desserts"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_desserts_price_non_negative"),
        CheckConstraint("old_price IS NULL OR old_price >= 0", name="ck_desserts_old_price_non_negative"),
        CheckConstraint("stock >= 0", name="ck_desserts_stock_non_negative"),
        CheckConstraint("rating_avg >= 0 AND rating_avg <= 5", name="ck_desserts_rating_avg_range"),
        CheckConstraint("reviews_count >= 0", name="ck_desserts_reviews_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingredients: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[DessertStatus] = mapped_column(
        sql_enum(DessertStatus, "dessert_status"),
        nullable=False,
        default=DessertStatus.ACTIVE,
        server_default=DessertStatus.ACTIVE.value,
        index=True,
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_best_seller: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=0, server_default="0")
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category = relationship("Category", back_populates="desserts")
    images = relationship("DessertImage", back_populates="dessert", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="dessert")
    reviews = relationship("Review", back_populates="dessert", cascade="all, delete-orphan")
