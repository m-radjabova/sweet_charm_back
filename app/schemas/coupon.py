from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.enums import CouponStatus, CouponType
from app.schemas.common import ORMModel


class CouponBase(ORMModel):
    code: str = Field(min_length=2, max_length=64)
    type: CouponType
    value: Decimal = Field(ge=0)
    minimum_order: Decimal = Field(default=0, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    start_date: date
    end_date: date
    status: CouponStatus = CouponStatus.ACTIVE

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return str(value).strip().upper()

    @model_validator(mode="after")
    def validate_coupon(self) -> "CouponBase":
        if self.start_date > self.end_date:
            raise ValueError("Start date cannot be later than end date")
        if self.type == CouponType.PERCENTAGE and not (Decimal("1") <= self.value <= Decimal("100")):
            raise ValueError("Percentage coupon value must be between 1 and 100")
        if self.type == CouponType.FIXED and self.value <= 0:
            raise ValueError("Fixed coupon value must be greater than 0")
        if self.type == CouponType.FREE_SHIPPING and self.value != 0:
            raise ValueError("Free shipping coupon value must be 0")
        return self


class CouponCreate(CouponBase):
    pass


class CouponUpdate(ORMModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    type: CouponType | None = None
    value: Decimal | None = Field(default=None, ge=0)
    minimum_order: Decimal | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    status: CouponStatus | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip().upper()

    @model_validator(mode="after")
    def validate_partial_coupon(self) -> "CouponUpdate":
        next_type = self.type
        next_value = self.value
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Start date cannot be later than end date")
        if next_type == CouponType.PERCENTAGE and next_value is not None and not (Decimal("1") <= next_value <= Decimal("100")):
            raise ValueError("Percentage coupon value must be between 1 and 100")
        if next_type == CouponType.FIXED and next_value is not None and next_value <= 0:
            raise ValueError("Fixed coupon value must be greater than 0")
        if next_type == CouponType.FREE_SHIPPING and next_value is not None and next_value != 0:
            raise ValueError("Free shipping coupon value must be 0")
        return self


class CouponOut(CouponBase):
    id: UUID
    assigned_user_id: UUID | None = None
    reward_tier: str | None = None
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime


class CouponListOut(ORMModel):
    items: list[CouponOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    total_active: int


class PublicCouponOut(ORMModel):
    id: UUID
    code: str
    type: CouponType
    value: Decimal
    minimum_order: Decimal
    usage_limit: int | None = None
    assigned_user_id: UUID | None = None
    reward_tier: str | None = None
    start_date: date
    end_date: date
