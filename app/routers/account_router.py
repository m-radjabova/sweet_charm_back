from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.address import AddressCreate, AddressOut, AddressUpdate
from app.schemas.order import OrderCreate, OrderOut
from app.schemas.reward_coupon import AccountCouponOut
from app.schemas.user import MyRewardsOut
from app.services.account_service import AccountService

router = APIRouter(prefix="/account", tags=["Account"])


@router.get("/orders", response_model=list[OrderOut])
def my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).list_my_orders(current_user)


@router.get("/rewards", response_model=MyRewardsOut)
def my_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).get_my_rewards(current_user)


@router.get("/coupons", response_model=list[AccountCouponOut])
def my_coupons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).list_my_coupons(current_user)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_my_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).create_my_order(current_user, payload)


@router.post("/orders/{order_id}/repeat", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def repeat_my_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).repeat_my_order(current_user, order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_my_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).cancel_my_order(current_user, order_id)


@router.get("/addresses", response_model=list[AddressOut])
def my_addresses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).list_my_addresses(current_user)


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_my_address(
    payload: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).create_my_address(current_user, payload)


@router.patch("/addresses/{address_id}", response_model=AddressOut)
def update_my_address(
    address_id: UUID,
    payload: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AccountService(db).update_my_address(current_user, address_id, payload)


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_address(
    address_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    AccountService(db).delete_my_address(current_user, address_id)
