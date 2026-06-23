from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.coupon import CouponCreate, CouponListOut, CouponOut, PublicCouponOut
from app.services.coupon_service import CouponService

router = APIRouter(prefix="/coupons", tags=["Coupons"])


@router.get("", response_model=CouponListOut)
def list_coupons(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CouponService(db).list_admin(
        page=page,
        page_size=page_size,
        search=search,
        status=status_filter,
    )


@router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(
    payload: CouponCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CouponService(db).create_coupon(payload)


@router.get("/active", response_model=list[PublicCouponOut])
def list_active_coupons(
    db: Session = Depends(get_db),
):
    return CouponService(db).list_public_active()
