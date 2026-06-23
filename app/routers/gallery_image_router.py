from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.gallery_image import GalleryImageOut
from app.services.gallery_image_service import GalleryImageService

router = APIRouter(prefix="/gallery-images", tags=["Gallery Images"])


@router.get("/active", response_model=list[GalleryImageOut])
def list_active_gallery_images(
    limit: int = Query(default=7, ge=1, le=12),
    db: Session = Depends(get_db),
):
    return GalleryImageService(db).list_active(limit=limit)
