from datetime import date, datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel, TimestampedSchema, validate_app_email
from app.utils.imagekit import build_imagekit_webp_url


class UserBase(ORMModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    birthday: date | None = None
    bio: str | None = Field(default=None, max_length=500)
    avatar: str | None = None
    role: UserRole
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)

    @field_validator("avatar")
    @classmethod
    def optimize_avatar(cls, value: str | None) -> str | None:
        return build_imagekit_webp_url(value, width=512, quality=82)


class AdminCreate(ORMModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)


class UserUpdate(ORMModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    email: str | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    birthday: date | None = None
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_app_email(value)


class ChangePasswordSchema(ORMModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class PointTransactionOut(ORMModel):
    id: UUID
    user_id: UUID
    order_id: UUID | None = None
    points: int
    type: str
    description: str
    created_at: datetime


class RewardLevelOut(ORMModel):
    key: str
    name: str
    min_points: int
    max_points: int | None = None
    reward_title: str | None = None
    unlocked: bool


class MyRewardsOut(ORMModel):
    sweet_points: int
    points_per_dollar: int
    current_level: RewardLevelOut
    next_level: RewardLevelOut | None = None
    next_reward_title: str | None = None
    points_to_next_level: int
    progress_percent: int
    levels: list[RewardLevelOut]
    transactions: list[PointTransactionOut]


class UserOut(TimestampedSchema, UserBase):
    sweet_points: int = 0
