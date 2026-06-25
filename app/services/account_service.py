from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import selectinload

from app.models.address import Address
from app.models.coupon import Coupon
from app.models.dessert import Dessert
from app.models.enums import CouponStatus, CouponType, DessertStatus, OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.reward_coupon import RewardCoupon
from app.models.user import User
from app.schemas.address import AddressCreate, AddressUpdate
from app.schemas.order import OrderCreate
from app.schemas.user import MyRewardsOut
from app.realtime import realtime_manager
from app.services.base import BaseService
from app.services.dessert_service import DessertService
from app.services.reward_coupon_service import RewardCouponService


class AccountService(BaseService):
    ORDER_CANCEL_WINDOW = timedelta(hours=2)
    MONEY_QUANT = Decimal("0.01")
    POINTS_PER_DOLLAR = Decimal("10")
    REWARD_COUPON_DURATION_DAYS = 90
    DIAMOND_REPEAT_STEP = 5000
    LEVELS = (
        {
            "key": "bronze",
            "name": "Bronze Bunny",
            "min_points": 0,
            "max_points": 999,
            "reward_title": None,
            "coupon_value": None,
        },
        {
            "key": "silver",
            "name": "Silver Bunny",
            "min_points": 1000,
            "max_points": 2499,
            "reward_title": "Free Drink",
            "coupon_value": None,
        },
        {
            "key": "gold",
            "name": "Gold Bunny",
            "min_points": 2500,
            "max_points": 4999,
            "reward_title": "$15 OFF Coupon",
            "coupon_value": Decimal("15.00"),
        },
        {
            "key": "diamond",
            "name": "Diamond Bunny",
            "min_points": 5000,
            "max_points": None,
            "reward_title": "$35 OFF Coupon",
            "coupon_value": Decimal("35.00"),
        },
    )

    def list_my_orders(self, user: User) -> list[Order]:
        statement = (
            select(Order)
            .where(Order.user_id == user.id)
            .options(selectinload(Order.items), selectinload(Order.user))
            .order_by(Order.created_at.desc())
        )
        orders = list(self.db.execute(statement).scalars().all())
        for order in orders:
            self._attach_cancel_metadata(order)
        return orders

    def get_my_rewards(self, user: User) -> dict:
        sweet_points = max(0, int(user.sweet_points or 0))
        current_level = self._get_current_level(sweet_points)
        next_level = self._get_next_level(sweet_points)
        progress_bounds = self._get_progress_bounds(sweet_points)
        progress_span = max(1, progress_bounds["end"] - progress_bounds["start"])
        progress_value = min(progress_span, max(0, sweet_points - progress_bounds["start"]))
        next_reward_title = self._get_next_reward_title(sweet_points, next_level)

        return {
            "sweet_points": sweet_points,
            "points_per_dollar": int(self.POINTS_PER_DOLLAR),
            "current_level": self._serialize_level(current_level, unlocked=True),
            "next_level": self._serialize_level(next_level, unlocked=False) if next_level else None,
            "next_reward_title": next_reward_title,
            "points_to_next_level": self._get_points_to_next_reward(sweet_points, next_level),
            "progress_percent": min(100, round((progress_value / progress_span) * 100)) if sweet_points else 0,
            "levels": [
                self._serialize_level(level, unlocked=sweet_points >= int(level["min_points"]))
                for level in self.LEVELS
            ],
            "transactions": self._list_point_transactions(user.id),
        }

    def list_my_coupons(self, user: User) -> list[dict]:
        reward_coupon_service = RewardCouponService(self.db)
        personal_coupons = reward_coupon_service.list_active_for_user(user.id)
        public_coupons = self._list_public_active_coupons()
        return [
            *[reward_coupon_service.serialize_account_coupon(coupon) for coupon in personal_coupons],
            *[self._serialize_public_coupon(coupon) for coupon in public_coupons],
        ]

    def create_my_order(self, user: User, payload: OrderCreate) -> Order:
        desserts = self._get_desserts_for_items(payload.items)
        subtotal = Decimal("0.00")
        order_items: list[OrderItem] = []
        touched_desserts: list[Dessert] = []

        dessert_map = {dessert.id: dessert for dessert in desserts}

        for item_payload in payload.items:
            dessert = dessert_map.get(item_payload.dessert_id)
            if dessert is None:
                raise self.not_found("Dessert")
            if dessert.stock < item_payload.quantity:
                raise self.bad_request(f"{dessert.name} has only {max(0, dessert.stock)} left in stock")

            line_price = Decimal(str(dessert.price))
            line_total = line_price * item_payload.quantity
            subtotal += line_total

            dessert.stock = max(0, int(dessert.stock) - int(item_payload.quantity))
            if dessert.stock <= 0:
                dessert.status = DessertStatus.OUT_OF_STOCK
            self.db.add(dessert)
            touched_desserts.append(dessert)

            order_items.append(
                OrderItem(
                    dessert_id=dessert.id,
                    dessert_name=dessert.name,
                    quantity=item_payload.quantity,
                    price=line_price,
                    total_price=line_total,
                )
            )

        delivery_price = Decimal("0.00")
        coupon = self._resolve_coupon(user, payload.coupon_code, subtotal, delivery_price)
        discount_amount = self._calculate_discount_amount(coupon, subtotal, delivery_price)
        payment_status = PaymentStatus.PAID if payload.payment_method.value == "card" else PaymentStatus.PENDING

        order = Order(
            user_id=user.id,
            customer_name=payload.customer_name,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            delivery_date=payload.delivery_date,
            delivery_time=payload.delivery_time,
            payment_method=payload.payment_method,
            payment_status=payment_status,
            subtotal=subtotal,
            delivery_price=delivery_price,
            coupon_code=coupon.code if coupon else None,
            discount_amount=discount_amount,
            total_price=max(Decimal("0.00"), subtotal + delivery_price - discount_amount),
            note=payload.note,
            items=order_items,
        )

        self.db.add(order)
        self.commit()

        statement = (
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.items), selectinload(Order.user))
        )
        created_order = self.db.execute(statement).scalar_one()
        self._attach_cancel_metadata(created_order)
        self._emit_order_created(created_order, user, coupon)
        if touched_desserts:
            DessertService(self.db)._emit_stock_update(touched_desserts)
        return created_order

    def repeat_my_order(self, user: User, order_id: UUID) -> Order:
        source_order = self._get_owned_order(user, order_id)
        if not source_order.items:
            raise self.bad_request("Order items not found")

        missing_item = next((item for item in source_order.items if item.dessert_id is None), None)
        if missing_item:
            raise self.bad_request("Some order items can no longer be repeated")

        payload = OrderCreate(
            customer_name=source_order.customer_name,
            phone=source_order.phone,
            email=source_order.email,
            address=source_order.address,
            delivery_date=source_order.delivery_date,
            delivery_time=source_order.delivery_time,
            payment_method=source_order.payment_method,
            coupon_code=None,
            note=source_order.note,
            items=[
                {
                    "dessert_id": item.dessert_id,
                    "quantity": item.quantity,
                }
                for item in source_order.items
            ],
        )
        return self.create_my_order(user, payload)

    def cancel_my_order(self, user: User, order_id: UUID) -> Order:
        order = self._get_owned_order(user, order_id)
        if order.status == OrderStatus.CANCELLED:
            raise self.bad_request("Order already cancelled")
        if order.status == OrderStatus.DELIVERED:
            raise self.bad_request("Delivered order cannot be cancelled")
        if not self._can_cancel_order(order):
            raise self.bad_request("Order can only be cancelled within 2 hours")

        touched_desserts = self._restore_stock_for_cancelled_order(order)
        order.status = OrderStatus.CANCELLED
        self.db.add(order)
        self.commit()
        refreshed = self.refresh(order)
        self._attach_cancel_metadata(refreshed)
        if touched_desserts:
            DessertService(self.db)._emit_stock_update(touched_desserts)
        return refreshed

    def _restore_stock_for_cancelled_order(self, order: Order) -> list[Dessert]:
        dessert_ids = [item.dessert_id for item in order.items if item.dessert_id is not None]
        if not dessert_ids:
            return []

        statement = select(Dessert).where(Dessert.id.in_(dessert_ids))
        desserts = list(self.db.execute(statement).scalars().all())
        dessert_map = {dessert.id: dessert for dessert in desserts}
        touched_desserts: list[Dessert] = []

        for item in order.items:
            if item.dessert_id is None:
                continue
            dessert = dessert_map.get(item.dessert_id)
            if dessert is None:
                continue

            dessert.stock = max(0, int(dessert.stock) + int(item.quantity))
            if dessert.stock > 0 and dessert.status == DessertStatus.OUT_OF_STOCK:
                dessert.status = DessertStatus.ACTIVE
            self.db.add(dessert)
            touched_desserts.append(dessert)

        return touched_desserts

    def list_my_addresses(self, user: User) -> list[Address]:
        statement = (
            select(Address)
            .where(Address.user_id == user.id)
            .order_by(Address.is_default.desc(), Address.created_at.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def create_my_address(self, user: User, payload: AddressCreate) -> Address:
        data = self._normalize_address_data(payload.model_dump())
        if data.get("is_default"):
            self._clear_default_addresses(user)

        address = Address(user_id=user.id, **data)
        self.db.add(address)
        self.commit()
        return self.refresh(address)

    def update_my_address(self, user: User, address_id: UUID, payload: AddressUpdate) -> Address:
        address = self._get_owned_address(user, address_id)
        data = self._normalize_address_data(payload.model_dump(exclude_unset=True))
        if data.get("is_default"):
            self._clear_default_addresses(user, exclude_address_id=address.id)

        for field, value in data.items():
            setattr(address, field, value)

        self.db.add(address)
        self.commit()
        return self.refresh(address)

    def delete_my_address(self, user: User, address_id: UUID) -> None:
        address = self._get_owned_address(user, address_id)
        self.db.delete(address)
        self.commit()

    def handle_order_delivered_rewards(self, order: Order) -> dict:
        if order.user_id is None or order.status != OrderStatus.DELIVERED:
            return {"awarded_points": 0, "unlocked_rewards": []}
        if self._has_order_points_transaction(order.id):
            return {"awarded_points": 0, "unlocked_rewards": []}

        user = order.user or self.db.get(User, order.user_id)
        if user is None:
            return {"awarded_points": 0, "unlocked_rewards": []}

        awarded_points = self._calculate_order_points(order.total_price)
        if awarded_points <= 0:
            return {"awarded_points": 0, "unlocked_rewards": []}

        previous_points = max(0, int(user.sweet_points or 0))
        user.sweet_points = previous_points + awarded_points
        user.current_level = str(self._get_current_level(user.sweet_points)["key"])
        self.db.add(user)
        unlocked_rewards: list[dict] = []

        self.db.execute(
            text(
                """
                INSERT INTO point_transactions (id, user_id, order_id, points, type, description)
                VALUES (:id, :user_id, :order_id, :points, :type, :description)
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": str(user.id),
                "order_id": str(order.id),
                "points": awarded_points,
                "type": "earned",
                "description": f"Earned {awarded_points} Sweet Points from order #{str(order.id)[:8]}",
            },
        )

        for level in self._get_newly_unlocked_levels(previous_points, user.sweet_points):
            reward = self._grant_level_reward(user, level)
            if reward:
                unlocked_rewards.append(reward)
        unlocked_rewards.extend(self._grant_repeat_diamond_rewards(user, previous_points, user.sweet_points))
        return {
            "awarded_points": awarded_points,
            "sweet_points": int(user.sweet_points or 0),
            "unlocked_rewards": unlocked_rewards,
            "summary": self.serialize_rewards_summary(user),
        }

    def _get_owned_address(self, user: User, address_id: UUID) -> Address:
        statement = select(Address).where(Address.id == address_id, Address.user_id == user.id)
        address = self.db.execute(statement).scalar_one_or_none()
        if not address:
            raise self.not_found("Address")
        return address

    def _clear_default_addresses(self, user: User, exclude_address_id: UUID | None = None) -> None:
        statement = update(Address).where(Address.user_id == user.id)
        if exclude_address_id:
            statement = statement.where(Address.id != exclude_address_id)
        self.db.execute(statement.values(is_default=False))

    def _get_desserts_for_items(self, items: list) -> list[Dessert]:
        dessert_ids = [item.dessert_id for item in items]
        statement = select(Dessert).where(Dessert.id.in_(dessert_ids))
        desserts = list(self.db.execute(statement).scalars().all())

        if len(desserts) != len(set(dessert_ids)):
            raise self.bad_request("One or more desserts could not be found")

        return desserts

    def _get_owned_order(self, user: User, order_id: UUID) -> Order:
        statement = (
            select(Order)
            .where(Order.id == order_id, Order.user_id == user.id)
            .options(selectinload(Order.items), selectinload(Order.user))
        )
        order = self.db.execute(statement).scalar_one_or_none()
        if not order:
            raise self.not_found("Order")
        return order

    def _resolve_coupon(
        self,
        user: User,
        coupon_code: str | None,
        subtotal: Decimal,
        delivery_price: Decimal,
    ) -> Coupon | RewardCoupon | None:
        if not coupon_code:
            return None

        reward_coupon_service = RewardCouponService(self.db)
        reward_coupon = reward_coupon_service.resolve_user_coupon(user, coupon_code, subtotal, delivery_price)
        if reward_coupon is not None:
            return reward_coupon

        marketing_coupon = self.db.execute(select(Coupon).where(Coupon.code == coupon_code)).scalar_one_or_none()
        coupon = marketing_coupon
        if coupon is None:
            raise self.bad_request("Coupon not found")

        today = datetime.now(UTC).date()
        if coupon.status != CouponStatus.ACTIVE:
            raise self.bad_request("Coupon is inactive")
        if coupon.start_date > today:
            raise self.bad_request("Coupon is not active yet")
        if coupon.end_date < today:
            raise self.bad_request("Coupon has expired")

        order_amount = subtotal + delivery_price
        if order_amount < Decimal(str(coupon.minimum_order)):
            raise self.bad_request(f"Minimum order for this coupon is ${Decimal(str(coupon.minimum_order)):.2f}")
        if coupon.usage_limit is not None:
            usage_count = self._get_coupon_usage_count(coupon.code)
            if usage_count >= coupon.usage_limit:
                raise self.bad_request("Coupon usage limit has been reached")

        return coupon

    def _calculate_discount_amount(
        self,
        coupon,
        subtotal: Decimal,
        delivery_price: Decimal,
    ) -> Decimal:
        if coupon is None:
            return Decimal("0.00")

        subtotal = Decimal(str(subtotal))
        delivery_price = Decimal(str(delivery_price))
        coupon_value = Decimal(str(coupon.value))

        if coupon.type == CouponType.PERCENTAGE:
            return (subtotal * coupon_value / Decimal("100")).quantize(self.MONEY_QUANT)
        if coupon.type == CouponType.FIXED:
            return min(coupon_value, subtotal + delivery_price).quantize(self.MONEY_QUANT)
        if coupon.type == CouponType.FREE_SHIPPING:
            return min(delivery_price, subtotal + delivery_price).quantize(self.MONEY_QUANT)
        return Decimal("0.00")

    def _get_coupon_usage_count(self, coupon_code: str) -> int:
        statement = select(func.count(Order.id)).where(
            Order.coupon_code == coupon_code,
            Order.status != OrderStatus.CANCELLED,
        )
        return int(self.db.execute(statement).scalar_one())

    def _get_coupon_usage_map(self, coupon_codes: list[str]) -> dict[str, int]:
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

    def _list_public_active_coupons(self) -> list[Coupon]:
        today = datetime.now(UTC).date()
        statement = (
            select(Coupon)
            .where(
                Coupon.status == CouponStatus.ACTIVE,
                Coupon.start_date <= today,
                Coupon.end_date >= today,
            )
            .order_by(Coupon.end_date.asc(), Coupon.created_at.desc())
        )
        coupons = list(self.db.execute(statement).scalars().all())
        return self._filter_visible_coupons(coupons)

    def _filter_visible_coupons(self, coupons: list, usage_limit_override: int | None = None) -> list:
        usage_map = self._get_coupon_usage_map([coupon.code for coupon in coupons])
        visible: list = []
        for coupon in coupons:
            usage_count = usage_map.get(coupon.code, 0)
            setattr(coupon, "usage_count", usage_count)
            usage_limit = usage_limit_override if usage_limit_override is not None else getattr(coupon, "usage_limit", None)
            if usage_limit is not None and usage_count >= usage_limit:
                continue
            visible.append(coupon)
        return visible

    def _list_point_transactions(self, user_id: UUID, limit: int = 8) -> list[dict]:
        rows = self.db.execute(
            text(
                """
                SELECT id, user_id, order_id, points, type, description, created_at
                FROM point_transactions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": str(user_id), "limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]

    def _has_order_points_transaction(self, order_id: UUID) -> bool:
        row = self.db.execute(
            text(
                """
                SELECT 1
                FROM point_transactions
                WHERE order_id = :order_id AND type = 'earned' AND points > 0
                LIMIT 1
                """
            ),
            {"order_id": str(order_id)},
        ).first()
        return row is not None

    def _has_reward_transaction(self, user_id: UUID, level_key: str) -> bool:
        row = self.db.execute(
            text(
                """
                SELECT 1
                FROM point_transactions
                WHERE user_id = :user_id AND description = :description
                LIMIT 1
                """
            ),
            {"user_id": str(user_id), "description": self._reward_unlock_description(level_key)},
        ).first()
        return row is not None

    def _has_claimed_reward(self, user_id: UUID, reward_type: str, threshold_points: int) -> bool:
        row = self.db.execute(
            text(
                """
                SELECT 1
                FROM user_rewards
                WHERE user_id = :user_id AND reward_type = :reward_type AND threshold_points = :threshold_points
                LIMIT 1
                """
            ),
            {
                "user_id": str(user_id),
                "reward_type": reward_type,
                "threshold_points": threshold_points,
            },
        ).first()
        if row is not None:
            return True

        legacy_level_key = reward_type.removeprefix("level_")
        if reward_type.startswith("level_"):
            return self._has_reward_transaction(user_id, legacy_level_key)
        return False

    def _record_reward_claim(self, user_id: UUID, reward_type: str, threshold_points: int) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO user_rewards (id, user_id, reward_type, threshold_points, claimed_at)
                VALUES (:id, :user_id, :reward_type, :threshold_points, NOW())
                ON CONFLICT (user_id, reward_type, threshold_points) DO NOTHING
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": str(user_id),
                "reward_type": reward_type,
                "threshold_points": threshold_points,
            },
        )

    def _calculate_order_points(self, total_price: Decimal) -> int:
        scaled = Decimal(str(total_price)) * self.POINTS_PER_DOLLAR
        return int(scaled.to_integral_value(rounding=ROUND_DOWN))

    def _get_newly_unlocked_levels(self, previous_points: int, current_points: int) -> list[dict]:
        return [
            level
            for level in self.LEVELS
            if previous_points < int(level["min_points"]) <= current_points and level["reward_title"]
        ]

    def _grant_level_reward(self, user: User, level: dict) -> dict | None:
        level_key = str(level["key"])
        threshold_points = int(level["min_points"])
        reward_type = f"level_{level_key}"
        if self._has_claimed_reward(user.id, reward_type, threshold_points):
            return None

        coupon_payload = None
        if level["coupon_value"] is not None:
            coupon_payload = self._create_reward_coupon(user, level)

        self.db.execute(
            text(
                """
                INSERT INTO point_transactions (id, user_id, order_id, points, type, description)
                VALUES (:id, :user_id, :order_id, :points, :type, :description)
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": str(user.id),
                "order_id": None,
                "points": 0,
                "type": "earned",
                "description": self._reward_unlock_description(level_key),
            },
        )
        self._record_reward_claim(user.id, reward_type, threshold_points)
        return {
            "reward_type": reward_type,
            "title": level["name"],
            "reward_title": level["reward_title"],
            "threshold_points": threshold_points,
            "coupon": coupon_payload,
        }

    def _grant_repeat_diamond_rewards(self, user: User, previous_points: int, current_points: int) -> list[dict]:
        if current_points < self.DIAMOND_REPEAT_STEP * 2:
            return []

        starting_threshold = max(self.DIAMOND_REPEAT_STEP * 2, ((previous_points // self.DIAMOND_REPEAT_STEP) + 1) * self.DIAMOND_REPEAT_STEP)
        final_threshold = (current_points // self.DIAMOND_REPEAT_STEP) * self.DIAMOND_REPEAT_STEP
        if final_threshold < starting_threshold:
            return []

        diamond_level = next(level for level in self.LEVELS if level["key"] == "diamond")
        unlocked_rewards: list[dict] = []
        for threshold in range(starting_threshold, final_threshold + 1, self.DIAMOND_REPEAT_STEP):
            reward_type = "diamond_repeat"
            if self._has_claimed_reward(user.id, reward_type, threshold):
                continue

            coupon_payload = self._create_reward_coupon(
                user,
                diamond_level,
                reward_tier="diamond_repeat",
                suffix=f"D{threshold // self.DIAMOND_REPEAT_STEP}",
                threshold_points=threshold,
            )
            self.db.execute(
                text(
                    """
                    INSERT INTO point_transactions (id, user_id, order_id, points, type, description)
                    VALUES (:id, :user_id, :order_id, :points, :type, :description)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user.id),
                    "order_id": None,
                    "points": 0,
                    "type": "earned",
                    "description": f"Unlocked Diamond bonus: $35 OFF Coupon at {threshold} pts",
                },
            )
            self._record_reward_claim(user.id, reward_type, threshold)
            unlocked_rewards.append(
                {
                    "reward_type": reward_type,
                    "title": "Diamond bonus",
                    "reward_title": "$35 OFF Coupon",
                    "threshold_points": threshold,
                    "coupon": coupon_payload,
                }
            )
        return unlocked_rewards

    def _create_reward_coupon(
        self,
        user: User,
        level: dict,
        *,
        reward_tier: str | None = None,
        suffix: str | None = None,
        threshold_points: int | None = None,
    ) -> dict | None:
        effective_reward_tier = reward_tier or str(level["key"])
        reward_coupon_service = RewardCouponService(self.db)
        existing = reward_coupon_service.find_existing_by_user_and_type(user.id, effective_reward_tier)
        if existing and reward_tier is None:
            return None

        today = datetime.now(UTC).date()
        coupon = reward_coupon_service.create_reward_coupon(
            user_id=user.id,
            value=Decimal(str(level["coupon_value"])).quantize(self.MONEY_QUANT),
            reward_type=effective_reward_tier,
            threshold_points=threshold_points if threshold_points is not None else int(level["min_points"]),
            expires_at=today + timedelta(days=self.REWARD_COUPON_DURATION_DAYS),
            code_hint=suffix,
        )
        self.db.flush()
        return jsonable_encoder(reward_coupon_service.serialize_account_coupon(coupon))

    def _get_current_level(self, sweet_points: int) -> dict:
        current_level = self.LEVELS[0]
        for level in self.LEVELS:
            if sweet_points >= int(level["min_points"]):
                current_level = level
        return current_level

    def _get_next_level(self, sweet_points: int) -> dict | None:
        for level in self.LEVELS:
            if sweet_points < int(level["min_points"]):
                return level
        return None

    def _get_points_to_next_reward(self, sweet_points: int, next_level: dict | None) -> int:
        if next_level is not None:
            return max(0, int(next_level["min_points"] - sweet_points))
        next_threshold = ((sweet_points // self.DIAMOND_REPEAT_STEP) + 1) * self.DIAMOND_REPEAT_STEP
        return max(0, next_threshold - sweet_points)

    def _get_next_reward_title(self, sweet_points: int, next_level: dict | None) -> str | None:
        if next_level is not None:
            return next_level["reward_title"]
        return "$35 OFF Coupon"

    def _get_progress_bounds(self, sweet_points: int) -> dict[str, int]:
        if sweet_points < self.DIAMOND_REPEAT_STEP:
            return {"start": 0, "end": self.DIAMOND_REPEAT_STEP}
        start = (sweet_points // self.DIAMOND_REPEAT_STEP) * self.DIAMOND_REPEAT_STEP
        if sweet_points % self.DIAMOND_REPEAT_STEP == 0:
            start = max(0, sweet_points - self.DIAMOND_REPEAT_STEP)
        return {"start": start, "end": start + self.DIAMOND_REPEAT_STEP}

    def _serialize_level(self, level: dict, *, unlocked: bool) -> dict:
        return {
            "key": level["key"],
            "name": level["name"],
            "min_points": int(level["min_points"]),
            "max_points": int(level["max_points"]) if level["max_points"] is not None else None,
            "reward_title": level["reward_title"],
            "unlocked": unlocked,
        }

    def _reward_unlock_description(self, level_key: str) -> str:
        level = next(item for item in self.LEVELS if item["key"] == level_key)
        reward_title = level["reward_title"] or "Reward"
        return f"Unlocked {level['name']} reward: {reward_title}"

    def _serialize_public_coupon(self, coupon: Coupon) -> dict:
        return {
            "id": coupon.id,
            "code": coupon.code,
            "type": coupon.type,
            "value": coupon.value,
            "minimum_order": coupon.minimum_order,
            "usage_limit": coupon.usage_limit,
            "assigned_user_id": None,
            "reward_tier": None,
            "start_date": coupon.start_date,
            "end_date": coupon.end_date,
        }

    def _attach_cancel_metadata(self, order: Order) -> None:
        cancel_deadline = order.created_at + self.ORDER_CANCEL_WINDOW
        setattr(order, "cancel_deadline", cancel_deadline)
        setattr(order, "can_cancel", self._can_cancel_order(order))

    def _can_cancel_order(self, order: Order) -> bool:
        if order.status in {OrderStatus.CANCELLED, OrderStatus.DELIVERED}:
            return False
        now = datetime.now(UTC)
        return now <= (order.created_at + self.ORDER_CANCEL_WINDOW)

    def _emit_order_created(self, order: Order, user: User, coupon: Coupon | RewardCoupon | None) -> None:
        order_id = str(order.id)
        realtime_manager.emit_to_admins_sync(
            "new_order",
            {
                "order_id": order_id,
            },
        )
        realtime_manager.emit_to_admins_sync(
            "notification_created",
            {
                "id": f"new-order-{order_id}",
                "kind": "new_order",
                "title": "New order received",
                "message": f"{order.customer_name} placed order #{order_id[:8]}.",
                "metadata": {
                    "order_id": order_id,
                    "total_price": str(order.total_price),
                },
            },
        )
        if coupon is not None:
            realtime_manager.emit_to_admins_sync(
                "notification_created",
                {
                    "id": f"coupon-used-{order_id}",
                    "kind": "coupon_used",
                    "title": "Coupon used",
                    "message": f"{order.customer_name} used coupon {coupon.code} on order #{order_id[:8]}.",
                    "metadata": {
                        "order_id": order_id,
                        "coupon_code": coupon.code,
                    },
                },
            )

    def serialize_rewards_summary(self, user: User) -> dict:
        return jsonable_encoder(MyRewardsOut.model_validate(self.get_my_rewards(user)))

    @staticmethod
    def _normalize_address_data(data: dict) -> dict:
        for key in ("title", "city", "street", "apartment", "note"):
            if key in data and data[key] is not None:
                data[key] = str(data[key]).strip() or None
        return data
