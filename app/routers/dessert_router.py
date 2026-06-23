from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import AdminDessertCreate, AdminDessertListOut, AdminDessertOut, AdminDessertUpdate
from app.schemas.dessert import FeaturedDessertOut
from app.services.admin_service import AdminService
from app.services.dessert_service import DessertService

router = APIRouter(prefix="/desserts", tags=["Desserts"])


@router.get("", response_model=list[FeaturedDessertOut])
def list_desserts(
    category: str | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    dietary: str | None = Query(default=None, min_length=1),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    return DessertService(db).list_all(
        category=category,
        min_price=min_price,
        max_price=max_price,
        dietary=dietary,
        min_rating=min_rating,
        search=search,
    )


@router.get("/categories", response_model=list[str])
def list_dessert_categories(db: Session = Depends(get_db)):
    return DessertService(db).list_categories()


@router.get("/featured", response_model=list[FeaturedDessertOut])
def list_featured_desserts(
    limit: int = Query(default=8, ge=1, le=16),
    db: Session = Depends(get_db),
):
    return DessertService(db).list_featured(limit=limit)


@router.get("/manage", response_model=AdminDessertListOut)
def list_desserts_for_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status: str | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).list_desserts(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        category_id=category_id,
    )


@router.post("", response_model=AdminDessertOut, status_code=status.HTTP_201_CREATED)
def create_dessert(
    payload: AdminDessertCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).create_dessert(payload)


@router.patch("/{dessert_id}", response_model=AdminDessertOut)
def update_dessert(
    dessert_id: UUID,
    payload: AdminDessertUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).update_dessert(dessert_id, payload)


@router.delete("/{dessert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dessert(
    dessert_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    AdminService(db).delete_dessert(dessert_id)
