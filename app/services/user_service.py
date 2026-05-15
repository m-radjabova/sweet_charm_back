from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

import requests
from fastapi import UploadFile, status
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import BarberCreate, BarberServiceItem, BarberUpdate, ChangePasswordSchema, UserUpdate
from app.services.base import BaseService, ServiceError
from app.services.telegram_service import TelegramService
from app.utils.imagekit import build_imagekit_webp_url


class UserService(BaseService):
    MAX_GALLERY_IMAGES = 12

    def get_user_by_id(self, user_id: str) -> User:
        try:
            user_uuid = UUID(str(user_id))
        except ValueError as exc:
            raise self.bad_request("Foydalanuvchi id noto'g'ri") from exc

        user = self.db.get(User, user_uuid)
        if not user:
            raise self.not_found("Foydalanuvchi")
        return user

    def get_barber_by_id(self, barber_id: str) -> User:
        barber = self.get_user_by_id(barber_id)
        if barber.role != UserRole.BARBER:
            raise self.bad_request("Bu foydalanuvchi barber emas")
        return barber

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email.strip().lower())
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_phone_number(self, phone_number: str) -> User | None:
        statement = select(User).where(User.phone_number == phone_number.strip())
        return self.db.execute(statement).scalar_one_or_none()

    def create_barber(self, payload: BarberCreate) -> User:
        return self._create_user(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            role=UserRole.BARBER,
        )

    def create_admin(self, full_name: str, email: str, password: str) -> User:
        return self._create_user(full_name=full_name, email=email, password=password, role=UserRole.ADMIN)

    def list_barbers(self) -> list[User]:
        statement = select(User).where(User.role == UserRole.BARBER).order_by(User.created_at.desc())
        return list(self.db.execute(statement).scalars().all())

    def update_current_user(self, current_user: User, payload: UserUpdate) -> User:
        previous_services = list(current_user.services or []) if current_user.role == UserRole.BARBER else []
        data = payload.model_dump(exclude_unset=True)
        if "email" in data:
            data["email"] = data["email"].strip().lower()
            self._ensure_email_available(data["email"], exclude_user_id=current_user.id)
        if "phone_number" in data and data["phone_number"] is not None:
            data["phone_number"] = self._normalize_phone_number(data["phone_number"])
            self._ensure_phone_number_available(data["phone_number"], exclude_user_id=current_user.id)
        if "specialty" in data:
            data["specialty"] = self._normalize_specialty(data["specialty"])
        if "bio" in data:
            data["bio"] = self._normalize_text_block(data["bio"])
        if "location_text" in data:
            data["location_text"] = self._normalize_short_text(data["location_text"])
        self._normalize_location_fields(data)
        if "services" in data and data["services"] is not None:
            data["services"] = self._normalize_services(data["services"])

        for field, value in data.items():
            setattr(current_user, field, value)

        self.db.add(current_user)
        self.commit()
        updated_user = self.refresh(current_user)

        if current_user.role == UserRole.BARBER and "services" in data:
            TelegramService(self.db).send_service_promotion_update(
                updated_user,
                previous_services,
                list(updated_user.services or []),
            )

        return updated_user

    def update_barber(self, barber_id: str, payload: BarberUpdate) -> User:
        barber = self.get_barber_by_id(barber_id)

        data = payload.model_dump(exclude_unset=True)
        if "email" in data:
            data["email"] = data["email"].strip().lower()
            self._ensure_email_available(data["email"], exclude_user_id=barber.id)
        if "specialty" in data:
            data["specialty"] = self._normalize_specialty(data["specialty"])
        if "bio" in data:
            data["bio"] = self._normalize_text_block(data["bio"])
        if "location_text" in data:
            data["location_text"] = self._normalize_short_text(data["location_text"])
        self._normalize_location_fields(data)
        if "services" in data and data["services"] is not None:
            data["services"] = self._normalize_services(data["services"])
        if "password" in data:
            data["password_hash"] = hash_password(data.pop("password"))

        for field, value in data.items():
            setattr(barber, field, value)

        self.db.add(barber)
        self.commit()
        return self.refresh(barber)

    def delete_barber(self, barber_id: str) -> None:
        barber = self.get_barber_by_id(barber_id)
        self.db.delete(barber)
        self.commit()

    def change_my_password(self, current_user: User, payload: ChangePasswordSchema) -> User:
        if not verify_password(payload.current_password, current_user.password_hash):
            raise self.bad_request("Joriy parol noto'g'ri")

        current_user.password_hash = hash_password(payload.new_password)
        current_user.refresh_token_hash = None
        self.db.add(current_user)
        self.commit()
        return self.refresh(current_user)

    def update_avatar(self, user: User, image: UploadFile) -> User:
        uploaded_url = self._upload_image(
            image,
            folder="/barber-shop/avatars",
            width=512,
            quality=82,
        )
        user.avatar = uploaded_url
        self.db.add(user)
        self.commit()
        return self.refresh(user)

    def delete_avatar(self, user: User) -> User:
        user.avatar = None
        self.db.add(user)
        self.commit()
        return self.refresh(user)

    def add_gallery_image(self, user: User, image: UploadFile) -> User:
        if user.role != UserRole.BARBER:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Faqat barber galereya yuklashi mumkin")

        current_images = list(user.gallery_images or [])
        if len(current_images) >= self.MAX_GALLERY_IMAGES:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Galereyada ko'pi bilan 12 ta rasm bo'lishi mumkin")

        uploaded_url = self._upload_image(
            image,
            folder="/barber-shop/gallery",
            width=1600,
            quality=82,
        )
        user.gallery_images = [*current_images, uploaded_url]
        self.db.add(user)
        self.commit()
        return self.refresh(user)

    def delete_gallery_image(self, user: User, image_index: int) -> User:
        if user.role != UserRole.BARBER:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Faqat barber galereyani o'zgartirishi mumkin")

        current_images = list(user.gallery_images or [])
        if image_index < 0 or image_index >= len(current_images):
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Rasm topilmadi")

        current_images.pop(image_index)
        user.gallery_images = current_images
        self.db.add(user)
        self.commit()
        return self.refresh(user)

    def _create_user(self, full_name: str, email: str, password: str, role: UserRole) -> User:
        normalized_email = email.strip().lower()
        self._ensure_email_available(normalized_email)

        user = User(
            full_name=full_name.strip(),
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
        )
        self.db.add(user)
        self.commit()
        return self.refresh(user)

    def _ensure_email_available(self, email: str, exclude_user_id=None) -> None:
        existing_user = self.get_by_email(email)
        if existing_user and existing_user.id != exclude_user_id:
            raise self.bad_request("Bu email allaqachon mavjud")

    def _ensure_phone_number_available(self, phone_number: str, exclude_user_id=None) -> None:
        existing_user = self.get_by_phone_number(phone_number)
        if existing_user and existing_user.id != exclude_user_id:
            raise self.bad_request("Bu telefon raqami allaqachon mavjud")

    @staticmethod
    def _normalize_specialty(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_short_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None

    @staticmethod
    def _normalize_text_block(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_services(items: list[BarberServiceItem | dict]) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for item in items:
            payload = item.model_dump() if isinstance(item, BarberServiceItem) else dict(item)
            name = " ".join(str(payload["name"]).strip().split())
            normalized.append(
                {
                    "name": name,
                    "price": int(payload["price"]),
                    "discount_price": (
                        int(payload["discount_price"])
                        if payload.get("discount_price") is not None
                        else None
                    ),
                    "promotion_text": UserService._normalize_short_text(payload.get("promotion_text")),
                    "duration_minutes": int(payload["duration_minutes"]),
                }
            )
        return normalized

    @staticmethod
    def _normalize_location_fields(data: dict[str, object]) -> None:
        has_lat = "location_lat" in data
        has_lng = "location_lng" in data

        if has_lat:
            data["location_lat"] = float(data["location_lat"]) if data["location_lat"] is not None else None
        if has_lng:
            data["location_lng"] = float(data["location_lng"]) if data["location_lng"] is not None else None

        if has_lat != has_lng:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Lokatsiya uchun latitude va longitude birga yuborilishi kerak")

        if has_lat and (data["location_lat"] is None or data["location_lng"] is None):
            data["location_lat"] = None
            data["location_lng"] = None

    @staticmethod
    def _normalize_phone_number(value: str) -> str:
        digits = "".join(char for char in value if char.isdigit())
        if digits.startswith("998"):
            digits = digits[3:]
        if len(digits) != 9:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Telefon raqami noto'g'ri")
        return f"+998{digits}"

    @staticmethod
    def _resolve_extension(filename: str, content_type: str) -> str:
        extension = Path(filename).suffix.lower().lstrip(".")
        if extension in {"jpg", "jpeg", "png", "webp"}:
            return "jpg" if extension == "jpeg" else extension

        content_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        return content_map.get(content_type, "jpg")

    def _upload_image(self, image: UploadFile, *, folder: str, width: int, quality: int = 80) -> str:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Faqat rasm yuklash mumkin")

        file_extension = self._resolve_extension(image.filename or "", image.content_type)
        filename = f"{uuid.uuid4().hex}.{file_extension}"
        image.file.seek(0)
        file_bytes = image.file.read()

        original_url = self._upload_to_imagekit(filename, file_bytes, folder=folder)
        return build_imagekit_webp_url(original_url, width=width, quality=quality) or original_url

    @staticmethod
    def _upload_to_imagekit(filename: str, file_bytes: bytes, *, folder: str) -> str:
        if not settings.IMAGEKIT_PRIVATE_KEY or not settings.IMAGEKIT_URL_ENDPOINT:
            raise ServiceError(status.HTTP_500_INTERNAL_SERVER_ERROR, "ImageKit sozlanmagan")

        response = requests.post(
            "https://upload.imagekit.io/api/v1/files/upload",
            auth=(settings.IMAGEKIT_PRIVATE_KEY, ""),
            files={"file": (filename, file_bytes)},
            data={
                "fileName": filename,
                "folder": folder,
                "useUniqueFileName": "true",
            },
            timeout=30,
        )

        if response.status_code >= 400:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Rasmni ImageKit'ga yuklab bo'lmadi")

        payload = response.json()
        url = payload.get("url")
        if not url:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "ImageKit URL qaytarmadi")
        return url
