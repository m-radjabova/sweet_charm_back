from pydantic import Field

from app.schemas.common import ORMModel


class BirthdayGreetingOut(ORMModel):
    show: bool = False
    name: str | None = None
    message: str | None = None


class BirthdayGreetingMarkShownOut(ORMModel):
    success: bool = True
    year: int = Field(ge=2000)
