from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.models.enums import CouponType
from app.schemas.common import ORMModel


class AccountCouponOut(ORMModel):
    id: UUID
    code: str
    type: CouponType
    value: Decimal
    minimum_order: Decimal
    usage_limit: int | None = None
    assigned_user_id: UUID | None = None
    reward_tier: str | None = None
    start_date: date
    end_date: date


class AdminRewardCouponOut(ORMModel):
    id: UUID
    customer_name: str
    reward: str
    code: str
    issued_date: datetime
    expire_date: date
    status: str
    value: Decimal
    usage_count: int = 0


class AdminRewardStatsOut(ORMModel):
    total_rewards: int
    used_rewards: int
    unused_rewards: int
    expired_rewards: int


class AdminRewardListOut(ORMModel):
    items: list[AdminRewardCouponOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminRewardStatsOut
