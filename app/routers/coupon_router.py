from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.coupon import CouponCreate, CouponListOut, CouponOut, CouponUpdate, PublicCouponOut
from app.schemas.reward_coupon import AdminRewardListOut
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


@router.get("/rewards", response_model=AdminRewardListOut)
def list_reward_coupons(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CouponService(db).list_admin_rewards(
        page=page,
        page_size=page_size,
        search=search,
    )


@router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(
    payload: CouponCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CouponService(db).create_coupon(payload)


@router.patch("/{coupon_id}", response_model=CouponOut)
def update_coupon(
    coupon_id: UUID,
    payload: CouponUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CouponService(db).update_coupon(coupon_id, payload)


@router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(
    coupon_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    CouponService(db).delete_coupon(coupon_id)


@router.get("/active", response_model=list[PublicCouponOut])
def list_active_coupons(
    db: Session = Depends(get_db),
):
    return CouponService(db).list_public_active()
