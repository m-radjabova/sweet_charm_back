from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.coupon import Coupon
from app.models.enums import CouponStatus, CouponType, OrderStatus
from app.models.order import Order
from app.schemas.coupon import CouponCreate, CouponUpdate
from app.services.base import BaseService
from app.services.reward_coupon_service import RewardCouponService


class CouponService(BaseService):
    def list_admin(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        statement = select(Coupon)
        if search:
            statement = statement.where(func.lower(Coupon.code).like(f"%{search.strip().lower()}%"))
        if status and status != "all":
            statement = statement.where(Coupon.status == status)

        total = self._count(statement)
        items = list(
            self.db.execute(
                statement.order_by(Coupon.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        usage_map = self._get_usage_map([coupon.code for coupon in items])
        for coupon in items:
            setattr(coupon, "usage_count", usage_map.get(coupon.code, 0))
        total_active = int(
            self.db.execute(
                select(func.count()).select_from(Coupon).where(
                    Coupon.status == CouponStatus.ACTIVE,
                )
            ).scalar_one()
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "total_active": total_active,
        }

    def list_admin_rewards(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
    ) -> dict:
        return RewardCouponService(self.db).list_admin_rewards(page=page, page_size=page_size, search=search)

    def create_coupon(self, payload: CouponCreate) -> Coupon:
        existing = self.db.execute(select(Coupon).where(Coupon.code == payload.code)).scalar_one_or_none()
        if existing or RewardCouponService(self.db).code_exists(payload.code):
            raise self.bad_request("Coupon code already exists")

        coupon = Coupon(
            code=payload.code,
            type=payload.type,
            value=payload.value,
            minimum_order=payload.minimum_order,
            usage_limit=payload.usage_limit,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=payload.status,
        )
        self.db.add(coupon)
        self.commit()
        return self.refresh(coupon)

    def update_coupon(self, coupon_id, payload: CouponUpdate) -> Coupon:
        coupon = self._get_admin_coupon(coupon_id)
        data = payload.model_dump(exclude_unset=True)
        next_type = data.get("type", coupon.type)
        next_value = data.get("value", coupon.value)
        next_start_date = data.get("start_date", coupon.start_date)
        next_end_date = data.get("end_date", coupon.end_date)

        if next_start_date > next_end_date:
            raise self.bad_request("Start date cannot be later than end date")
        if next_type == CouponType.FREE_SHIPPING:
            next_value = 0
            data["value"] = 0
        elif next_type == CouponType.PERCENTAGE and not (1 <= float(next_value) <= 100):
            raise self.bad_request("Percentage coupon value must be between 1 and 100")
        elif next_type == CouponType.FIXED and float(next_value) <= 0:
            raise self.bad_request("Fixed coupon value must be greater than 0")

        next_code = data.get("code")
        if next_code and next_code != coupon.code:
            existing = self.db.execute(select(Coupon).where(Coupon.code == next_code)).scalar_one_or_none()
            if existing or RewardCouponService(self.db).code_exists(next_code):
                raise self.bad_request("Coupon code already exists")

        for field, value in data.items():
            setattr(coupon, field, value)

        self.db.add(coupon)
        self.commit()
        return self.refresh(coupon)

    def delete_coupon(self, coupon_id) -> None:
        coupon = self._get_admin_coupon(coupon_id)
        self.db.delete(coupon)
        self.commit()

    def list_public_active(self) -> list[Coupon]:
        today = date.today()
        statement = (
            select(Coupon)
            .where(
                Coupon.status == CouponStatus.ACTIVE,
                Coupon.start_date <= today,
                Coupon.end_date >= today,
            )
            .order_by(Coupon.end_date.asc(), Coupon.created_at.desc())
        )
        items = list(self.db.execute(statement).scalars().all())
        usage_map = self._get_usage_map([coupon.code for coupon in items])
        visible_items: list[Coupon] = []
        for coupon in items:
            usage_count = usage_map.get(coupon.code, 0)
            setattr(coupon, "usage_count", usage_count)
            if coupon.usage_limit is not None and usage_count >= coupon.usage_limit:
                continue
            visible_items.append(coupon)
        return visible_items

    def _count(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _get_usage_map(self, coupon_codes: list[str]) -> dict[str, int]:
        codes = [code for code in coupon_codes if code]
        if not codes:
            return {}

        statement = (
            select(Order.coupon_code, func.count(Order.id))
            .where(
                Order.coupon_code.in_(codes),
                Order.status != OrderStatus.CANCELLED,
            )
            .group_by(Order.coupon_code)
        )
        rows = self.db.execute(statement).all()
        return {str(code): int(count) for code, count in rows if code}

    def _get_admin_coupon(self, coupon_id) -> Coupon:
        coupon = self.db.get(Coupon, coupon_id)
        if coupon is None:
            raise self.not_found("Coupon")
        return coupon

def get_coupon_service(db: Session) -> CouponService:
    return CouponService(db)
