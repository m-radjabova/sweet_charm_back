from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.birthday_greeting import BirthdayGreeting
from app.models.user import User
from app.schemas.birthday_greeting import BirthdayGreetingOut
from app.services.base import BaseService


class BirthdayGreetingService(BaseService):
    DEFAULT_MESSAGE = "Wishing you a day filled with joy, laughter, and sweet moments."

    def get_greeting(self, user: User) -> dict:
        today = datetime.now(UTC).date()
        birthday = user.birthday
        current_year = today.year

        if birthday is None:
            return BirthdayGreetingOut(show=False).model_dump()

        if birthday.month != today.month:
            return BirthdayGreetingOut(show=False).model_dump()

        already_shown = self._get_year_record(user.id, current_year)
        if already_shown is not None:
            return BirthdayGreetingOut(show=False).model_dump()

        first_name = (user.full_name or "").strip().split(" ")[0] if user.full_name else "Sweet Friend"
        return BirthdayGreetingOut(
            show=True,
            name=first_name,
            message=self.DEFAULT_MESSAGE,
        ).model_dump()

    def mark_shown(self, user: User) -> dict:
        today = datetime.now(UTC).date()
        current_year = today.year

        existing = self._get_year_record(user.id, current_year)
        if existing is None:
            record = BirthdayGreeting(user_id=user.id, year=current_year)
            self.db.add(record)
            self.commit()

        return {
            "success": True,
            "year": current_year,
        }

    def _get_year_record(self, user_id, year: int) -> BirthdayGreeting | None:
        statement = select(BirthdayGreeting).where(
            BirthdayGreeting.user_id == user_id,
            BirthdayGreeting.year == year,
        )
        return self.db.execute(statement).scalar_one_or_none()
