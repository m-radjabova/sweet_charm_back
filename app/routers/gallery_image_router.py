from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import (
    AdminGalleryImageCreate,
    AdminGalleryImageListOut,
    AdminGalleryImageOut,
    AdminGalleryImageUpdate,
)
from app.schemas.gallery_image import GalleryImageOut
from app.services.gallery_image_service import GalleryImageService

router = APIRouter(prefix="/gallery-images", tags=["Gallery Images"])


class GalleryUploadOut(BaseModel):
    url: str
    file_id: str | None = None


@router.get("/active", response_model=list[GalleryImageOut])
def list_active_gallery_images(
    limit: int = Query(default=7, ge=1, le=12),
    db: Session = Depends(get_db),
):
    return GalleryImageService(db).list_active(limit=limit)


@router.post("/upload", response_model=GalleryUploadOut)
def upload_gallery_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    url, file_id = GalleryImageService(db).upload_image(image)
    return GalleryUploadOut(url=url, file_id=file_id)


@router.get("", response_model=AdminGalleryImageListOut)
def list_gallery_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return GalleryImageService(db).list_admin(
        page=page,
        page_size=page_size,
        search=search,
        status=status_filter,
    )


@router.post("", response_model=AdminGalleryImageOut, status_code=status.HTTP_201_CREATED)
def create_gallery_image(
    payload: AdminGalleryImageCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return GalleryImageService(db).create(payload)


@router.patch("/{image_id}", response_model=AdminGalleryImageOut)
def update_gallery_image(
    image_id: UUID,
    payload: AdminGalleryImageUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return GalleryImageService(db).update(image_id, payload)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gallery_image(
    image_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    GalleryImageService(db).delete(image_id)
