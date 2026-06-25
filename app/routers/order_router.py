from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import AdminOrderListOut, AdminOrderOut, AdminOrderUpdate
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=AdminOrderListOut)
def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return OrderService(db).list_admin(page=page, page_size=page_size, search=search, status=status)


@router.patch("/{order_id}", response_model=AdminOrderOut)
def update_order(
    order_id: UUID,
    payload: AdminOrderUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return OrderService(db).update_admin(order_id, payload)
