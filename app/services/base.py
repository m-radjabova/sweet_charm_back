from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class ServiceError(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class BaseService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def not_found(entity: str) -> ServiceError:
        return ServiceError(status.HTTP_404_NOT_FOUND, f"{entity} topilmadi")

    @staticmethod
    def bad_request(message: str) -> ServiceError:
        return ServiceError(status.HTTP_400_BAD_REQUEST, message)

    @staticmethod
    def forbidden(message: str) -> ServiceError:
        return ServiceError(status.HTTP_403_FORBIDDEN, message)

    def commit(self):
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise self.bad_request(self._get_constraint_message(exc)) from exc

    def refresh(self, instance):
        self.db.refresh(instance)
        return instance

    @staticmethod
    def _get_constraint_message(exc: IntegrityError) -> str:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)
        raw_message = str(getattr(exc, "orig", exc)).lower()

        if constraint_name == "users_email_key" or "users_email_key" in raw_message:
            return "Bu email allaqachon mavjud"

        if constraint_name in {"users_phone_key", "users_phone_number_key"} or "users_phone_key" in raw_message:
            return "Bu telefon raqami allaqachon ro'yxatdan o'tgan"

        return "Ma'lumotlar cheklovi buzildi"
