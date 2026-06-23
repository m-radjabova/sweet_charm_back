from pydantic import BaseModel, Field, field_validator

from app.schemas.common import validate_app_email


class LoginSchema(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return value.strip().lower()


class RegisterSchema(BaseModel):
    full_name: str
    email: str
    phone: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("To'liq ism kamida 3 ta belgi bo'lishi kerak")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 7:
            raise ValueError("Telefon raqami noto'g'ri")
        return normalized


class RefreshSchema(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
