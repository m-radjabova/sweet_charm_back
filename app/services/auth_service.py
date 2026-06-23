from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.jwt import create_token, decode_token
from app.core.security import hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import LoginSchema, RegisterSchema
from app.services.base import BaseService, ServiceError


class AuthService(BaseService):
    def login(self, payload: LoginSchema) -> dict:
        normalized_email = payload.email.strip().lower()
        statement = select(User).where(func.lower(User.email) == normalized_email)
        user = self.db.execute(statement).scalar_one_or_none()
        if not user or not verify_password(payload.password, user.password_hash):
            raise ServiceError(401, "Invalid credentials")
        if not user.is_active:
            raise ServiceError(403, "User is inactive")

        return self._issue_tokens(user)

    def register(self, payload: RegisterSchema) -> dict:
        normalized_phone = self._normalize_phone(payload.phone)
        normalized_email = payload.email.strip().lower()

        phone_statement = select(User).where(User.phone == normalized_phone)
        existing_phone_user = self.db.execute(phone_statement).scalar_one_or_none()
        if existing_phone_user is not None:
            raise ServiceError(409, "Bu telefon raqami allaqachon ro'yxatdan o'tgan")

        email_statement = select(User).where(func.lower(User.email) == normalized_email)
        existing_email_user = self.db.execute(email_statement).scalar_one_or_none()
        if existing_email_user is not None:
            raise ServiceError(409, "Bu email allaqachon mavjud")

        user = User(
            full_name=payload.full_name.strip(),
            email=normalized_email,
            phone=normalized_phone,
            password_hash=hash_password(payload.password),
            role=UserRole.USER,
            is_active=True,
        )
        return self._issue_tokens(user)

    def refresh_access_token(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise ServiceError(401, "Invalid refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise ServiceError(401, "Invalid refresh token payload")

        try:
            user_uuid = UUID(str(user_id))
        except (TypeError, ValueError) as exc:
            raise ServiceError(401, "Invalid refresh token payload") from exc

        user = self.db.get(User, user_uuid)
        if not user or not user.refresh_token_hash:
            raise ServiceError(401, "Refresh token expired")
        if not verify_password(refresh_token, user.refresh_token_hash):
            raise ServiceError(401, "Refresh token mismatch")
        if not user.is_active:
            raise ServiceError(403, "User is inactive")

        return {
            "access_token": create_token(
                payload={
                    "sub": str(user.id),
                    "type": "access",
                    "role": user.role.value,
                },
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            ),
            "token_type": "bearer",
        }

    def logout(self, user: User) -> None:
        user.refresh_token_hash = None
        self.db.add(user)
        self.commit()

    def _issue_tokens(self, user: User) -> dict:
        if not user.is_active:
            raise ServiceError(403, "User is inactive")

        tokens = self._build_tokens(user)
        user.refresh_token_hash = hash_password(tokens["refresh_token"])
        self.db.add(user)
        self.commit()
        return tokens

    def _build_tokens(self, user: User) -> dict:
        access_token = create_token(
            payload={
                "sub": str(user.id),
                "type": "access",
                "role": user.role.value,
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh_token = create_token(
            payload={"sub": str(user.id), "type": "refresh"},
            expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        digits = "".join(char for char in phone if char.isdigit())
        if digits.startswith("998"):
            digits = digits[3:]
        if len(digits) != 9:
            raise ServiceError(400, "Telefon raqamini +998 XX XXX XX XX formatida kiriting")
        return f"+998{digits}"


def get_auth_service(db: Session) -> AuthService:
    return AuthService(db)
