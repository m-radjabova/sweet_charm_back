from __future__ import annotations

from datetime import datetime, time

from pydantic import Field, field_validator, model_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel, TimestampedSchema, validate_app_email
from app.utils.imagekit import build_imagekit_webp_url


class UserBase(ORMModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    phone_number: str | None = Field(default=None, min_length=7, max_length=32)
    avatar: str | None = None
    gallery_images: list[str] = Field(default_factory=list)
    specialty: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=1200)
    location_text: str | None = Field(default=None, max_length=255)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    work_start_time: time | None = None
    work_end_time: time | None = None
    services: list[BarberServiceItem] = Field(default_factory=list)
    telegram_notifications_enabled: bool = False
    telegram_marketing_enabled: bool = False
    telegram_connected_at: datetime | None = None
    role: UserRole
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)

    @field_validator("services", mode="before")
    @classmethod
    def normalize_services(cls, value):
        return value or []

    @field_validator("avatar")
    @classmethod
    def optimize_avatar(cls, value: str | None) -> str | None:
        return build_imagekit_webp_url(value, width=512, quality=82)

    @field_validator("gallery_images", mode="before")
    @classmethod
    def normalize_gallery_images(cls, value):
        if not value:
            return []
        images = [value] if isinstance(value, str) else list(value)
        return [
            optimized
            for image in images
            if image and (optimized := build_imagekit_webp_url(str(image), width=1600, quality=82))
        ]


class BarberCreate(ORMModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)


class BarberServiceItem(ORMModel):
    name: str = Field(min_length=2, max_length=120)
    price: int = Field(ge=0, le=100000000)
    discount_price: int | None = Field(default=None, ge=0, le=100000000)
    promotion_text: str | None = Field(default=None, max_length=160)
    duration_minutes: int = Field(ge=10, le=360)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_discount(self) -> "BarberServiceItem":
        if self.discount_price is not None and self.discount_price > self.price:
            raise ValueError("Aksiya narxi asosiy narxdan katta bo'lishi mumkin emas")
        return self


class UserUpdate(ORMModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    email: str | None = None
    phone_number: str | None = Field(default=None, min_length=7, max_length=32)
    specialty: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=1200)
    location_text: str | None = Field(default=None, max_length=255)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    work_start_time: time | None = None
    work_end_time: time | None = None
    services: list[BarberServiceItem] | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_app_email(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "UserUpdate":
        if self.work_start_time and self.work_end_time and self.work_start_time >= self.work_end_time:
            raise ValueError("Ish vaqti noto'g'ri")
        return self


class BarberUpdate(ORMModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    email: str | None = None
    specialty: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=1200)
    location_text: str | None = Field(default=None, max_length=255)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    work_start_time: time | None = None
    work_end_time: time | None = None
    services: list[BarberServiceItem] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_app_email(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "BarberUpdate":
        if self.work_start_time and self.work_end_time and self.work_start_time >= self.work_end_time:
            raise ValueError("Ish vaqti noto'g'ri")
        return self


class ChangePasswordSchema(ORMModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UserOut(TimestampedSchema, UserBase):
    telegram_connected: bool = False


class TelegramLinkOut(ORMModel):
    connected: bool
    bot_username: str | None = None
    bot_url: str | None = None
    deep_link_url: str | None = None
    token_expires_at: datetime | None = None
    telegram_connected_at: datetime | None = None
    telegram_notifications_enabled: bool
    telegram_marketing_enabled: bool
    subscribers_count: int = 0


class TelegramPromotionCreate(ORMModel):
    title: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=3, max_length=600)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Xabar bo'sh bo'lishi mumkin emas")
        return normalized


class TelegramPromotionResultOut(ORMModel):
    total_recipients: int
    delivered_recipients: int
    failed_recipients: int
