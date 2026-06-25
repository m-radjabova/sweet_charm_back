from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.coupon import Coupon
from app.models.enums import CouponStatus, CouponType, OrderStatus
from app.models.order import Order
from app.models.reward_coupon import RewardCoupon
from app.models.user import User
from app.services.base import BaseService


class RewardCouponService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)

    def list_admin_rewards(self, page: int = 1, page_size: int = 10, search: str | None = None) -> dict:
        today = datetime.now(UTC).date()
        usage_counts = func.count(Order.id)
        base_statement = (
            select(
                RewardCoupon.id,
                RewardCoupon.code,
                RewardCoupon.value,
                RewardCoupon.expires_at,
                RewardCoupon.issued_at,
                User.full_name.label("customer_name"),
                usage_counts.label("usage_count"),
            )
            .join(User, RewardCoupon.user_id == User.id)
            .outerjoin(
                Order,
                (Order.coupon_code == RewardCoupon.code) & (Order.status != OrderStatus.CANCELLED),
            )
            .group_by(RewardCoupon.id, User.full_name)
        )
        if search:
            term = f"%{search.strip().lower()}%"
            base_statement = base_statement.where(
                or_(
                    func.lower(RewardCoupon.code).like(term),
                    func.lower(User.full_name).like(term),
                )
            )

        rows = self.db.execute(
            base_statement.order_by(RewardCoupon.issued_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = [self._serialize_admin_reward(row, today=today) for row in rows]
        total = self._count(base_statement)

        stats_row = self.db.execute(
            select(
                func.count(RewardCoupon.id).label("total_rewards"),
                func.sum(case((((Order.id.is_(None)) & (RewardCoupon.expires_at < today)), 1), else_=0)).label("expired_rewards"),
                func.sum(case((Order.id.is_not(None), 1), else_=0)).label("used_rewards"),
                func.sum(case(((RewardCoupon.expires_at >= today) & Order.id.is_(None), 1), else_=0)).label("unused_rewards"),
            )
            .select_from(RewardCoupon)
            .outerjoin(
                Order,
                (Order.coupon_code == RewardCoupon.code) & (Order.status != OrderStatus.CANCELLED),
            )
            .where(RewardCoupon.status == CouponStatus.ACTIVE)
        ).mappings().one()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "stats": {
                "total_rewards": int(stats_row["total_rewards"] or 0),
                "used_rewards": int(stats_row["used_rewards"] or 0),
                "unused_rewards": int(stats_row["unused_rewards"] or 0),
                "expired_rewards": int(stats_row["expired_rewards"] or 0),
            },
        }

    def list_active_for_user(self, user_id: UUID) -> list[RewardCoupon]:
        today = datetime.now(UTC).date()
        statement = (
            select(RewardCoupon)
            .where(
                RewardCoupon.status == CouponStatus.ACTIVE,
                RewardCoupon.user_id == user_id,
                RewardCoupon.expires_at >= today,
            )
            .order_by(RewardCoupon.issued_at.desc())
        )
        coupons = list(self.db.execute(statement).scalars().all())
        return self._filter_visible_reward_coupons(coupons)

    def resolve_user_coupon(
        self,
        user: User,
        coupon_code: str | None,
        subtotal: Decimal,
        delivery_price: Decimal,
    ) -> RewardCoupon | None:
        if not coupon_code:
            return None

        coupon = self.db.execute(select(RewardCoupon).where(RewardCoupon.code == coupon_code)).scalar_one_or_none()
        if coupon is None:
            return None

        today = datetime.now(UTC).date()
        if coupon.user_id != user.id:
            raise self.bad_request("Coupon does not belong to this account")
        if coupon.status != CouponStatus.ACTIVE:
            raise self.bad_request("Coupon is inactive")
        if coupon.expires_at < today:
            raise self.bad_request("Coupon has expired")
        if subtotal + delivery_price < Decimal(str(coupon.minimum_order)):
            raise self.bad_request(f"Minimum order for this coupon is ${Decimal(str(coupon.minimum_order)):.2f}")
        if self.get_usage_count(coupon.code) >= 1:
            raise self.bad_request("Coupon usage limit has been reached")
        return coupon

    def create_reward_coupon(
        self,
        *,
        user_id: UUID,
        value: Decimal,
        reward_type: str,
        threshold_points: int,
        expires_at: date,
        issued_at: datetime | None = None,
        minimum_order: Decimal = Decimal("0.00"),
        status: CouponStatus = CouponStatus.ACTIVE,
        code_hint: str | None = None,
    ) -> RewardCoupon:
        coupon = RewardCoupon(
            user_id=user_id,
            code=self.generate_code(reward_type, suffix=code_hint),
            type=CouponType.FIXED,
            value=value,
            minimum_order=minimum_order,
            reward_type=reward_type,
            threshold_points=threshold_points,
            status=status,
            issued_at=issued_at or datetime.now(UTC),
            expires_at=expires_at,
        )
        self.db.add(coupon)
        return coupon

    def find_existing_by_user_and_type(self, user_id: UUID, reward_type: str) -> RewardCoupon | None:
        return self.db.execute(
            select(RewardCoupon).where(
                RewardCoupon.user_id == user_id,
                RewardCoupon.reward_type == reward_type,
            )
        ).scalar_one_or_none()

    def code_exists(self, code: str) -> bool:
        return self.db.execute(select(RewardCoupon.id).where(RewardCoupon.code == code)).first() is not None

    def generate_code(self, reward_type: str, *, suffix: str | None = None) -> str:
        prefix_root = "".join(ch for ch in reward_type.upper() if ch.isalnum())[:6] or "RWD"
        prefix = suffix if suffix else prefix_root
        while True:
            code = f"RWD-{prefix}-{uuid4().hex[:6].upper()}"
            marketing_exists = self.db.execute(select(Coupon.id).where(Coupon.code == code)).first()
            reward_exists = self.db.execute(select(RewardCoupon.id).where(RewardCoupon.code == code)).first()
            if marketing_exists is None and reward_exists is None:
                return code

    def serialize_account_coupon(self, coupon: RewardCoupon) -> dict:
        reward_tier = "diamond" if coupon.reward_type.startswith("diamond") else coupon.reward_type.removeprefix("level_")
        issued_date = coupon.issued_at.date() if isinstance(coupon.issued_at, datetime) else datetime.now(UTC).date()
        return {
            "id": coupon.id,
            "code": coupon.code,
            "type": coupon.type,
            "value": coupon.value,
            "minimum_order": coupon.minimum_order,
            "usage_limit": 1,
            "assigned_user_id": coupon.user_id,
            "reward_tier": reward_tier,
            "start_date": issued_date,
            "end_date": coupon.expires_at,
        }

    def get_usage_count(self, coupon_code: str) -> int:
        statement = select(func.count(Order.id)).where(
            Order.coupon_code == coupon_code,
            Order.status != OrderStatus.CANCELLED,
        )
        return int(self.db.execute(statement).scalar_one())

    def get_usage_map(self, coupon_codes: list[str]) -> dict[str, int]:
        codes = [code for code in coupon_codes if code]
        if not codes:
            return {}
        rows = self.db.execute(
            select(Order.coupon_code, func.count(Order.id))
            .where(Order.coupon_code.in_(codes), Order.status != OrderStatus.CANCELLED)
            .group_by(Order.coupon_code)
        ).all()
        return {str(code): int(count) for code, count in rows if code}

    def _filter_visible_reward_coupons(self, coupons: list[RewardCoupon]) -> list[RewardCoupon]:
        usage_map = self.get_usage_map([coupon.code for coupon in coupons])
        visible: list[RewardCoupon] = []
        for coupon in coupons:
            usage_count = usage_map.get(coupon.code, 0)
            setattr(coupon, "usage_count", usage_count)
            if usage_count >= 1:
                continue
            visible.append(coupon)
        return visible

    def _count(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _serialize_admin_reward(self, row, *, today: date) -> dict:
        usage_count = int(row.usage_count or 0)
        if usage_count > 0:
            status = "used"
        elif row.expires_at < today:
            status = "expired"
        else:
            status = "unused"
        return {
            "id": row.id,
            "customer_name": row.customer_name,
            "reward": f"${row.value:.0f} OFF",
            "code": row.code,
            "issued_date": row.issued_at,
            "expire_date": row.expires_at,
            "status": status,
            "value": row.value,
            "usage_count": usage_count,
        }
