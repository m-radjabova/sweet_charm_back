from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.schemas.common import ORMModel, validate_app_email


class OrderItemCreate(ORMModel):
    dessert_id: UUID
    quantity: int = Field(ge=1, le=99)


class OrderCreate(ORMModel):
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str = Field(min_length=5, max_length=500)
    delivery_date: date | None = None
    delivery_time: time | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    coupon_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    items: list[OrderItemCreate] = Field(min_length=1)

    @field_validator("customer_name", "phone", "address", "note", "coupon_code", mode="before")
    @classmethod
    def strip_text_fields(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()

    @field_validator("coupon_code")
    @classmethod
    def normalize_coupon_code(cls, value: str | None):
        if value is None or not value.strip():
            return None
        return value.strip().upper()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None):
        if value is None or not value.strip():
            return None
        return validate_app_email(value)

    @model_validator(mode="after")
    def validate_delivery_fields(self) -> "OrderCreate":
        if self.delivery_time and not self.delivery_date:
            raise ValueError("Delivery date is required when delivery time is selected")
        return self


class OrderItemOut(ORMModel):
    id: UUID
    dessert_id: UUID | None = None
    dessert_name: str
    quantity: int
    price: Decimal
    total_price: Decimal


class OrderOut(ORMModel):
    id: UUID
    customer_name: str
    phone: str
    email: str | None = None
    address: str
    delivery_date: date | None = None
    delivery_time: time | None = None
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    status: OrderStatus
    subtotal: Decimal
    delivery_price: Decimal
    coupon_code: str | None = None
    discount_amount: Decimal
    total_price: Decimal
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    cancel_deadline: datetime | None = None
    can_cancel: bool = False
    items: list[OrderItemOut] = []
