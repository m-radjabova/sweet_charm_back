from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import requests
from fastapi import UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.admin import AdminCreateUser
from app.schemas.user import AdminCreate, ChangePasswordSchema, UserUpdate
from app.services.base import BaseService, ServiceError
from app.utils.imagekit import build_imagekit_webp_url


class UserService(BaseService):
    MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
    ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def get_user_by_id(self, user_id: str) -> User:
        try:
            user_uuid = UUID(str(user_id))
        except ValueError as exc:
            raise self.bad_request("Foydalanuvchi id noto'g'ri") from exc

        user = self.db.get(User, user_uuid)
        if not user:
            raise self.not_found("Foydalanuvchi")
        return user

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email.strip().lower())
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_phone(self, phone: str) -> User | None:
        statement = select(User).where(User.phone == phone.strip())
        return self.db.execute(statement).scalar_one_or_none()

    def create_admin(self, payload: AdminCreate) -> User:
        return self._create_user(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            role=UserRole.ADMIN,
        )

    def create_admin_user(self, payload: AdminCreateUser) -> User:
        return self._create_user(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            role=UserRole.ADMIN,
        )

    def update_current_user(self, current_user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)
        if "email" in data:
            data["email"] = data["email"].strip().lower()
            self._ensure_email_available(data["email"], exclude_user_id=current_user.id)
        if "phone" in data and data["phone"] is not None:
            data["phone"] = self._normalize_phone(data["phone"])
            self._ensure_phone_available(data["phone"], exclude_user_id=current_user.id)
        if "bio" in data and data["bio"] is not None:
            data["bio"] = data["bio"].strip() or None

        for field, value in data.items():
            setattr(current_user, field, value)

        self.db.add(current_user)
        self.commit()
        return self.refresh(current_user)

    def change_my_password(self, current_user: User, payload: ChangePasswordSchema) -> User:
        if not verify_password(payload.current_password, current_user.password_hash):
            raise self.bad_request("Joriy parol noto'g'ri")

        current_user.password_hash = hash_password(payload.new_password)
        current_user.refresh_token_hash = None
        self.db.add(current_user)
        self.commit()
        return self.refresh(current_user)

    def update_avatar(self, user: User, image: UploadFile) -> User:
        uploaded_url, uploaded_file_id = self._upload_image(
            image,
            folder="/sweet-charm/avatars",
            width=512,
            quality=82,
        )
        previous_file_id = user.avatar_file_id
        user.avatar = uploaded_url
        user.avatar_file_id = uploaded_file_id
        self.db.add(user)
        self.commit()
        if previous_file_id and previous_file_id != uploaded_file_id:
            self._delete_from_imagekit(previous_file_id)
        return self.refresh(user)

    def delete_avatar(self, user: User) -> User:
        previous_file_id = user.avatar_file_id
        user.avatar = None
        user.avatar_file_id = None
        self.db.add(user)
        self.commit()
        if previous_file_id:
            self._delete_from_imagekit(previous_file_id)
        return self.refresh(user)

    def list_customers(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        filters = [User.role == UserRole.USER]
        if status == "active":
            filters.append(User.is_active.is_(True))
        elif status == "inactive":
            filters.append(User.is_active.is_(False))
        if search:
            query = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(
                    func.concat(
                        User.full_name,
                        " ",
                        User.email,
                        " ",
                        func.coalesce(User.phone, ""),
                    )
                ).like(query)
            )

        base_statement = (
            select(User)
            .options(selectinload(User.orders), selectinload(User.reviews))
            .where(*filters)
        )
        total = self._count_from_statement(base_statement)
        users = list(
            self.db.execute(
                base_statement.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_customer(user) for user in users],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_customer_stats(),
        }

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

    def _serialize_customer(self, user: User) -> dict:
        return {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "avatar": user.avatar,
            "role": user.role,
            "is_active": user.is_active,
            "birthday": user.birthday,
            "bio": user.bio,
            "orders_count": len(user.orders),
            "reviews_count": len(user.reviews),
            "created_at": user.created_at,
        }

    def _build_customer_stats(self) -> dict:
        users = list(
            self.db.execute(select(User.is_active, User.created_at).where(User.role == UserRole.USER)).all()
        )
        total = len(users)
        active = sum(1 for is_active, _ in users if is_active)
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = sum(1 for _, created_at in users if created_at >= month_start)
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "new_this_month": new_this_month,
        }

    def _count_from_statement(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _ensure_email_available(self, email: str, exclude_user_id=None) -> None:
        existing_user = self.get_by_email(email)
        if existing_user and existing_user.id != exclude_user_id:
            raise self.bad_request("Bu email allaqachon mavjud")

    def _ensure_phone_available(self, phone: str, exclude_user_id=None) -> None:
        existing_user = self.get_by_phone(phone)
        if existing_user and existing_user.id != exclude_user_id:
            raise self.bad_request("Bu telefon raqami allaqachon mavjud")

    @staticmethod
    def _normalize_phone(value: str) -> str:
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

    def _upload_image(self, image: UploadFile, *, folder: str, width: int, quality: int = 80) -> tuple[str, str | None]:
        if not image.content_type or image.content_type not in self.ALLOWED_IMAGE_CONTENT_TYPES:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Faqat rasm yuklash mumkin")

        file_extension = self._resolve_extension(image.filename or "", image.content_type)
        filename = f"{uuid.uuid4().hex}.{file_extension}"
        image.file.seek(0)
        file_bytes = image.file.read()

        if not file_bytes:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Bo'sh fayl yuklab bo'lmaydi")

        if len(file_bytes) > self.MAX_AVATAR_SIZE_BYTES:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Rasm hajmi 5MB dan katta bo'lmasligi kerak")

        original_url, file_id = self._upload_to_imagekit(filename, file_bytes, folder=folder)
        optimized_url = build_imagekit_webp_url(original_url, width=width, quality=quality) or original_url
        return optimized_url, file_id

    @staticmethod
    def _upload_to_imagekit(filename: str, file_bytes: bytes, *, folder: str) -> tuple[str, str | None]:
        if not settings.IMAGEKIT_PRIVATE_KEY or not settings.IMAGEKIT_URL_ENDPOINT:
            raise ServiceError(status.HTTP_500_INTERNAL_SERVER_ERROR, "ImageKit sozlanmagan")

        try:
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
        except requests.RequestException as exc:
            raise ServiceError(status.HTTP_502_BAD_GATEWAY, f"ImageKit bilan ulanishda xatolik: {exc}") from exc

        if response.status_code >= 400:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                f"ImageKit upload xatosi ({response.status_code}): {response.text[:300]}",
            )

        data = response.json()
        uploaded_url = data.get("url")
        if not uploaded_url:
            raise ServiceError(status.HTTP_502_BAD_GATEWAY, "ImageKit javobi noto'g'ri")
        return uploaded_url, data.get("fileId")

    @staticmethod
    def _delete_from_imagekit(file_id: str) -> None:
        if not settings.IMAGEKIT_PRIVATE_KEY:
            return

        try:
            requests.delete(
                f"https://api.imagekit.io/v1/files/{file_id}",
                auth=(settings.IMAGEKIT_PRIVATE_KEY, ""),
                timeout=15,
            )
        except requests.RequestException:
            return
