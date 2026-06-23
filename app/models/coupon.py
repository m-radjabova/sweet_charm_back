import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CouponStatus, CouponType, sql_enum


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("value >= 0", name="ck_coupons_value_non_negative"),
        CheckConstraint("minimum_order >= 0", name="ck_coupons_minimum_order_non_negative"),
        CheckConstraint("usage_limit IS NULL OR usage_limit >= 1", name="ck_coupons_usage_limit_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    type: Mapped[CouponType] = mapped_column(sql_enum(CouponType, "coupon_type"), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    minimum_order: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    usage_limit: Mapped[int | None] = mapped_column(nullable=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reward_tier: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CouponStatus] = mapped_column(
        sql_enum(CouponStatus, "coupon_status"),
        nullable=False,
        default=CouponStatus.ACTIVE,
        server_default=CouponStatus.ACTIVE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
