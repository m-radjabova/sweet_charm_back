from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import (
    AdminCategoryCreate,
    AdminCategoryListOut,
    AdminCategoryOptionOut,
    AdminCategoryOut,
    AdminCategoryUpdate,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("/options", response_model=list[AdminCategoryOptionOut])
def list_category_options(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).list_category_options()


@router.get("", response_model=AdminCategoryListOut)
def list_categories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).list_categories(page=page, page_size=page_size, search=search, status=status)


@router.post("", response_model=AdminCategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: AdminCategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).create_category(payload)


@router.patch("/{category_id}", response_model=AdminCategoryOut)
def update_category(
    category_id: UUID,
    payload: AdminCategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).update_category(category_id, payload)


@router.post("/{category_id}/image", response_model=AdminCategoryOut)
def upload_category_image(
    category_id: UUID,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).upload_category_image(category_id, image)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    AdminService(db).delete_category(category_id)
