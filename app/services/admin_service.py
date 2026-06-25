from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.dessert import Dessert
from app.models.enums import OrderStatus, PaymentMethod, UserRole
from app.models.order import Order
from app.models.review import Review
from app.models.user import User
from app.services.base import BaseService


class AdminService(BaseService):
    def get_dashboard(self) -> dict:
        orders = list(
            self.db.execute(
                select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc())
            ).scalars().all()
        )
        reviews = list(
            self.db.execute(
                select(Review)
                .options(selectinload(Review.dessert), selectinload(Review.user))
                .order_by(Review.created_at.desc())
            ).scalars().all()
        )
        desserts = list(self.db.execute(select(Dessert).options(selectinload(Dessert.category))).scalars().all())
        categories = list(self.db.execute(select(Category)).scalars().all())
        users = list(
            self.db.execute(
                select(User).where(User.role == UserRole.USER).order_by(User.created_at.desc())
            ).scalars().all()
        )

        total_revenue = sum((Decimal(str(order.total_price)) for order in orders), Decimal("0"))
        status_counts = defaultdict(int)
        payment_counts = defaultdict(int)
        rating_counts = defaultdict(int)
        category_counts = defaultdict(int)
        revenue_by_category_map = defaultdict(Decimal)
        dessert_category_map = {
            dessert.id: dessert.category.name if dessert.category else "Uncategorized"
            for dessert in desserts
        }
        approved_reviews = [review for review in reviews if review.is_approved]
        pending_reviews_count = 0
        average_rating = (
            round(sum(review.rating for review in approved_reviews) / len(approved_reviews), 1)
            if approved_reviews
            else 0
        )

        for order in orders:
            status_counts[order.status.value] += 1
            payment_counts[order.payment_method.value] += 1
            for item in order.items:
                category_name = dessert_category_map.get(item.dessert_id, "Uncategorized")
                revenue_by_category_map[category_name] += Decimal(str(item.total_price))

        for review in reviews:
            rating_counts[str(review.rating)] += 1
            if not review.is_approved:
                pending_reviews_count += 1

        for dessert in desserts:
            category_name = dessert_category_map[dessert.id]
            category_counts[category_name] += 1

        orders_timeline = []
        revenue_timeline = []
        now = datetime.now(UTC)
        for offset in range(6, -1, -1):
            day_start = (now - timedelta(days=offset)).date()
            day_orders = [order for order in orders if order.created_at.date() == day_start]
            orders_timeline.append({"label": day_start.strftime("%d %b"), "value": len(day_orders)})
            revenue_timeline.append(
                {
                    "label": day_start.strftime("%d %b"),
                    "value": float(sum((Decimal(str(order.total_price)) for order in day_orders), Decimal("0"))),
                }
            )

        sales_overview = {
            "daily": revenue_timeline,
            "weekly": self._build_weekly_revenue_series(orders, now),
            "monthly": self._build_monthly_revenue_series(orders, now),
        }
        new_customers_growth = {
            "daily": self._build_daily_user_series(users, now),
            "weekly": self._build_weekly_user_series(users, now),
            "monthly": self._build_monthly_user_series(users, now),
        }
        orders_by_time = self._build_orders_heatmap(orders)

        top_desserts_map: dict[str, dict] = {}
        for order in orders:
            for item in order.items:
                key = str(item.dessert_id or item.id)
                if key not in top_desserts_map:
                    top_desserts_map[key] = {
                        "dessert_id": item.dessert_id,
                        "dessert_name": item.dessert_name,
                        "orders_count": 0,
                        "revenue": Decimal("0"),
                    }
                top_desserts_map[key]["orders_count"] += item.quantity
                top_desserts_map[key]["revenue"] += Decimal(str(item.total_price))

        top_desserts = sorted(
            top_desserts_map.values(),
            key=lambda entry: (entry["orders_count"], entry["revenue"]),
            reverse=True,
        )[:5]

        recent_orders = [
            {
                "id": order.id,
                "customer_name": order.customer_name,
                "total_price": order.total_price,
                "status": order.status,
                "created_at": order.created_at,
            }
            for order in orders[:6]
        ]

        active_users = sum(1 for user in users if user.is_active)
        low_stock_items = [
            {
                "id": dessert.id,
                "name": dessert.name,
                "slug": dessert.slug,
                "stock": max(0, int(dessert.stock or 0)),
                "status": dessert.status,
                "category_name": dessert.category.name if dessert.category else None,
            }
            for dessert in desserts
            if 0 < int(dessert.stock or 0) < 5
        ]
        low_stock_items.sort(key=lambda item: (item["stock"], item["name"]))

        return {
            "total_revenue": total_revenue,
            "total_orders": len(orders),
            "pending_orders": status_counts[OrderStatus.PENDING.value],
            "delivered_orders": status_counts[OrderStatus.DELIVERED.value],
            "low_stock_count": len(low_stock_items),
            "pending_reviews": pending_reviews_count,
            "approved_reviews": len(approved_reviews),
            "total_desserts": len(desserts),
            "total_categories": len(categories),
            "active_users": active_users,
            "average_rating": average_rating,
            "sales_overview": sales_overview,
            "new_customers_growth": new_customers_growth,
            "orders_timeline": orders_timeline,
            "revenue_timeline": revenue_timeline,
            "order_status_breakdown": [
                {"key": status.value, "label": status.value.replace("_", " ").title(), "value": status_counts[status.value]}
                for status in OrderStatus
            ],
            "payment_method_breakdown": [
                {
                    "key": method.value,
                    "label": method.value.replace("_", " ").title(),
                    "value": payment_counts[method.value],
                }
                for method in PaymentMethod
            ],
            "review_rating_breakdown": [
                {"key": str(rating), "label": f"{rating} stars", "value": rating_counts[str(rating)]}
                for rating in range(5, 0, -1)
            ],
            "category_distribution": [
                {"key": name.lower().replace(" ", "-"), "label": name, "value": count}
                for name, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "revenue_by_category": [
                {
                    "key": name.lower().replace(" ", "-"),
                    "label": name,
                    "value": int(revenue.quantize(Decimal("1"))),
                }
                for name, revenue in sorted(revenue_by_category_map.items(), key=lambda item: item[1], reverse=True)
            ],
            "orders_by_time": orders_by_time,
            "top_desserts": top_desserts,
            "recent_orders": recent_orders,
            "low_stock_items": low_stock_items[:6],
        }

    @staticmethod
    def _build_weekly_revenue_series(orders: list[Order], now: datetime) -> list[dict]:
        points: list[dict] = []
        for offset in range(7, -1, -1):
            week_start = (now - timedelta(days=offset * 7)).date()
            week_end = week_start + timedelta(days=6)
            week_orders = [order for order in orders if week_start <= order.created_at.date() <= week_end]
            points.append(
                {
                    "label": week_start.strftime("%d %b"),
                    "value": float(sum((Decimal(str(order.total_price)) for order in week_orders), Decimal("0"))),
                }
            )
        return points

    @staticmethod
    def _build_monthly_revenue_series(orders: list[Order], now: datetime) -> list[dict]:
        points: list[dict] = []
        month_cursor = now.replace(day=1)
        for offset in range(5, -1, -1):
            cursor = AdminService._shift_month(month_cursor, -offset)
            month_orders = [
                order
                for order in orders
                if order.created_at.year == cursor.year and order.created_at.month == cursor.month
            ]
            points.append(
                {
                    "label": cursor.strftime("%b"),
                    "value": float(sum((Decimal(str(order.total_price)) for order in month_orders), Decimal("0"))),
                }
            )
        return points

    @staticmethod
    def _build_daily_user_series(users: list[User], now: datetime) -> list[dict]:
        return [
            {
                "label": (now - timedelta(days=offset)).date().strftime("%d %b"),
                "value": len([user for user in users if user.created_at.date() == (now - timedelta(days=offset)).date()]),
            }
            for offset in range(6, -1, -1)
        ]

    @staticmethod
    def _build_weekly_user_series(users: list[User], now: datetime) -> list[dict]:
        points: list[dict] = []
        for offset in range(7, -1, -1):
            week_start = (now - timedelta(days=offset * 7)).date()
            week_end = week_start + timedelta(days=6)
            points.append(
                {
                    "label": week_start.strftime("%d %b"),
                    "value": len([user for user in users if week_start <= user.created_at.date() <= week_end]),
                }
            )
        return points

    @staticmethod
    def _build_monthly_user_series(users: list[User], now: datetime) -> list[dict]:
        points: list[dict] = []
        month_cursor = now.replace(day=1)
        for offset in range(5, -1, -1):
            cursor = AdminService._shift_month(month_cursor, -offset)
            points.append(
                {
                    "label": cursor.strftime("%b"),
                    "value": len(
                        [
                            user
                            for user in users
                            if user.created_at.year == cursor.year and user.created_at.month == cursor.month
                        ]
                    ),
                }
            )
        return points

    @staticmethod
    def _build_orders_heatmap(orders: list[Order]) -> list[dict]:
        slots = [8, 10, 12, 14, 16, 18, 20, 22]
        rows: list[dict] = []
        for weekday, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            rows.append(
                {
                    "day": day_name,
                    "slots": [
                        {
                            "time": f"{hour:02d}:00",
                            "value": len(
                                [
                                    order
                                    for order in orders
                                    if order.created_at.weekday() == weekday and abs(order.created_at.hour - hour) <= 1
                                ]
                            ),
                        }
                        for hour in slots
                    ],
                }
            )
        return rows

    @staticmethod
    def _shift_month(base: datetime, months_delta: int) -> datetime:
        month_index = (base.month - 1) + months_delta
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        return base.replace(year=year, month=month, day=1)


def get_admin_service(db: Session) -> AdminService:
    return AdminService(db)
