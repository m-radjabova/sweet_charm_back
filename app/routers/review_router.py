from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user, get_current_user_optional
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import AdminReviewListOut, AdminReviewOut, AdminReviewUpdate
from app.schemas.review import DessertReviewOut, FeaturedReviewOut, ReviewCreate
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/featured", response_model=list[FeaturedReviewOut])
def list_featured_reviews(
    limit: int = Query(default=6, ge=1, le=12),
    db: Session = Depends(get_db),
):
    return ReviewService(db).list_featured(limit=limit)


@router.get("/desserts/{dessert_slug}", response_model=list[DessertReviewOut])
def list_dessert_reviews(
    dessert_slug: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    return ReviewService(db).list_for_dessert(dessert_slug, current_user)


@router.post("/desserts/{dessert_slug}", response_model=DessertReviewOut)
def create_dessert_review(
    dessert_slug: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ReviewService(db).create_for_dessert(dessert_slug, current_user, payload)


@router.get("", response_model=AdminReviewListOut)
def list_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return ReviewService(db).list_admin(page=page, page_size=page_size, search=search, state=state)


@router.patch("/{review_id}", response_model=AdminReviewOut)
def update_review(
    review_id: UUID,
    payload: AdminReviewUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return ReviewService(db).update_admin(review_id, payload.is_approved)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    ReviewService(db).delete_admin(review_id)
