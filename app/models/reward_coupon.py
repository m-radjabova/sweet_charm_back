import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CouponStatus, CouponType, sql_enum


class RewardCoupon(Base):
    __tablename__ = "reward_coupons"
    __table_args__ = (
        CheckConstraint("value >= 0", name="ck_reward_coupons_value_non_negative"),
        CheckConstraint("minimum_order >= 0", name="ck_reward_coupons_minimum_order_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    type: Mapped[CouponType] = mapped_column(
        sql_enum(CouponType, "coupon_type"),
        nullable=False,
        default=CouponType.FIXED,
        server_default=CouponType.FIXED.value,
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    minimum_order: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    reward_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    threshold_points: Mapped[int] = mapped_column(nullable=False, index=True)
    status: Mapped[CouponStatus] = mapped_column(
        sql_enum(CouponStatus, "coupon_status"),
        nullable=False,
        default=CouponStatus.ACTIVE,
        server_default=CouponStatus.ACTIVE.value,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
