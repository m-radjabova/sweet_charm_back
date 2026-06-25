from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.services.dessert_service import DessertService


class UploadOut(BaseModel):
    url: str
    file_id: str | None = None


router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/images", response_model=UploadOut)
def upload_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    url, file_id = DessertService(db).upload_image(image)
    return UploadOut(url=url, file_id=file_id)
