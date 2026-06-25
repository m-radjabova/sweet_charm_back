from __future__ import annotations

from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.admin import AdminOrderOut
from app.schemas.admin import AdminOrderUpdate
from app.realtime import realtime_manager
from app.services.account_service import AccountService
from app.services.base import BaseService


class OrderService(BaseService):
    def list_admin(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        filters = []
        base_statement = select(Order).options(selectinload(Order.items), selectinload(Order.user))

        if status and status != "all":
            if status == "processing":
                filters.append(Order.status.in_([OrderStatus.PREPARING, OrderStatus.READY]))
            elif status == "pending":
                filters.append(Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED]))
            else:
                filters.append(Order.status == status)
        if search:
            query = f"%{search.strip().lower()}%"
            base_statement = base_statement.join(OrderItem, OrderItem.order_id == Order.id, isouter=True)
            filters.append(
                or_(
                    func.lower(func.cast(Order.id, String)).like(query),
                    func.lower(Order.customer_name).like(query),
                    func.lower(func.coalesce(Order.email, "")).like(query),
                    func.lower(Order.phone).like(query),
                    func.lower(Order.address).like(query),
                    func.lower(func.coalesce(OrderItem.dessert_name, "")).like(query),
                )
            )
        if filters:
            base_statement = base_statement.where(*filters)
        if search:
            base_statement = base_statement.distinct(Order.id)

        total = self._count_from_statement(base_statement)
        orders = list(
            self.db.execute(
                base_statement.order_by(Order.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().unique().all()
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_stats(),
        }

    def update_admin(self, order_id: UUID, payload: AdminOrderUpdate) -> Order:
        order = self._get(order_id)
        previous_status = order.status
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(order, field, value)
        reward_result = {"awarded_points": 0, "unlocked_rewards": []}
        if previous_status != OrderStatus.DELIVERED and order.status == OrderStatus.DELIVERED:
            reward_result = AccountService(self.db).handle_order_delivered_rewards(order)
        self.db.add(order)
        self.commit()
        refreshed = self._get(order_id)
        self._emit_order_status_change(refreshed, previous_status, reward_result)
        return refreshed

    def _get(self, order_id: UUID) -> Order:
        order = self.db.execute(
            select(Order).options(selectinload(Order.items), selectinload(Order.user)).where(Order.id == order_id)
        ).scalar_one_or_none()
        if not order:
            raise self.not_found("Order")
        return order

    def _build_stats(self) -> dict:
        orders = list(self.db.execute(select(Order.status)).all())
        total = len(orders)
        pending = sum(1 for (status,) in orders if status in {OrderStatus.PENDING, OrderStatus.CONFIRMED})
        processing = sum(1 for (status,) in orders if status in {OrderStatus.PREPARING, OrderStatus.READY})
        delivered = sum(1 for (status,) in orders if status == OrderStatus.DELIVERED)
        cancelled = sum(1 for (status,) in orders if status == OrderStatus.CANCELLED)
        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "delivered": delivered,
            "cancelled": cancelled,
        }

    def _count_from_statement(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _emit_order_status_change(self, order: Order, previous_status: OrderStatus, reward_result: dict) -> None:
        serialized_order = jsonable_encoder(AdminOrderOut.model_validate(order))
        payload = {
            "order_id": str(order.id),
            "previous_status": previous_status.value,
            "current_status": order.status.value,
            "order": serialized_order,
        }
        realtime_manager.emit_to_admins_sync("order_status_updated", payload)
        if order.user_id:
            realtime_manager.emit_to_user_sync(order.user_id, "order_status_updated", payload)

            if order.status == OrderStatus.CONFIRMED:
                realtime_manager.emit_to_user_sync(
                    order.user_id,
                    "notification_created",
                    {
                        "id": f"order-confirmed-{order.id}",
                        "kind": "order_confirmed",
                        "title": "Order confirmed",
                        "message": f"Your order #{str(order.id)[:8]} is now confirmed.",
                        "metadata": payload,
                    },
                )

            if order.status == OrderStatus.DELIVERED:
                realtime_manager.emit_to_user_sync(
                    order.user_id,
                    "notification_created",
                    {
                        "id": f"order-delivered-{order.id}",
                        "kind": "order_delivered",
                        "title": "Order delivered",
                        "message": f"Your order #{str(order.id)[:8]} has been delivered.",
                        "metadata": payload,
                    },
                )

                awarded_points = int(reward_result.get("awarded_points") or 0)
                summary = reward_result.get("summary")
                if awarded_points > 0 and summary:
                    realtime_manager.emit_to_user_sync(
                        order.user_id,
                        "points_updated",
                        {
                            "order_id": str(order.id),
                            "points_earned": awarded_points,
                            "summary": summary,
                        },
                    )
                    realtime_manager.emit_to_user_sync(
                        order.user_id,
                        "notification_created",
                        {
                            "id": f"points-earned-{order.id}",
                            "kind": "points_earned",
                            "title": f"+{awarded_points} Sweet Points",
                            "message": f"You earned {awarded_points} Sweet Points from order #{str(order.id)[:8]}.",
                            "metadata": {
                                "order_id": str(order.id),
                                "points_earned": awarded_points,
                            },
                        },
                    )

                for unlocked_reward in reward_result.get("unlocked_rewards") or []:
                    reward_payload = {
                        "order_id": str(order.id),
                        "summary": summary,
                        **unlocked_reward,
                    }
                    realtime_manager.emit_to_user_sync(order.user_id, "reward_unlocked", reward_payload)
                    realtime_manager.emit_to_user_sync(
                        order.user_id,
                        "notification_created",
                        {
                            "id": f"reward-unlocked-{order.id}-{unlocked_reward['reward_type']}-{unlocked_reward['threshold_points']}",
                            "kind": "reward_unlocked",
                            "title": f"{unlocked_reward['title']} unlocked",
                            "message": unlocked_reward["reward_title"] or "A new reward is ready for you.",
                            "metadata": reward_payload,
                        },
                    )
                    if unlocked_reward.get("coupon"):
                        realtime_manager.emit_to_user_sync(
                            order.user_id,
                            "notification_created",
                            {
                                "id": f"coupon-received-{order.id}-{unlocked_reward['threshold_points']}",
                                "kind": "coupon_received",
                                "title": "Coupon received",
                                "message": f"Your new reward coupon {unlocked_reward['coupon']['code']} is ready to use.",
                                "metadata": unlocked_reward["coupon"],
                            },
                        )


def get_order_service(db: Session) -> OrderService:
    return OrderService(db)
