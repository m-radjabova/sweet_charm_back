from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.birthday_greeting import BirthdayGreetingMarkShownOut, BirthdayGreetingOut
from app.services.birthday_greeting_service import BirthdayGreetingService

router = APIRouter(prefix="/birthday-greeting", tags=["Birthday Greeting"])


@router.get("", response_model=BirthdayGreetingOut)
def get_birthday_greeting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return BirthdayGreetingService(db).get_greeting(current_user)


@router.post("/mark-shown", response_model=BirthdayGreetingMarkShownOut)
def mark_birthday_greeting_shown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return BirthdayGreetingService(db).mark_shown(current_user)
