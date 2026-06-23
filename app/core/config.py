import os
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    value = value.strip()
    if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
        return int(value)

    raise ValueError(f"Invalid integer for {name}: {value!r}")


def _get_list_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _get_int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = _get_int_env("REFRESH_TOKEN_EXPIRE_DAYS", 7)
    CORS_ORIGINS: list[str] = _get_list_env(
        "CORS_ORIGINS",
        [
            "http://localhost:5173",
            "http://localhost:8081",
            "http://127.0.0.1:8081",
        ],
    )
    IMAGEKIT_PUBLIC_KEY: str = os.getenv("IMAGEKIT_PUBLIC_KEY", "").strip()
    IMAGEKIT_PRIVATE_KEY: str = os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip()
    IMAGEKIT_URL_ENDPOINT: str = os.getenv("IMAGEKIT_URL_ENDPOINT", "").strip().rstrip("/")
    AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", "").strip().lower() in {"1", "true", "yes"}
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Tashkent").strip() or "Asia/Tashkent"

    @property
    def app_timezone(self) -> ZoneInfo:
        return ZoneInfo(self.APP_TIMEZONE)


settings = Settings()
