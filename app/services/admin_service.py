from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.dessert import Dessert
from app.models.dessert_image import DessertImage
from app.models.enums import DessertStatus, OrderStatus, PaymentMethod, PaymentStatus, UserRole
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.review import Review
from app.models.user import User
from app.schemas.admin import (
    AdminCategoryCreate,
    AdminCategoryUpdate,
    AdminCreateUser,
    AdminDessertCreate,
    AdminDessertUpdate,
    AdminOrderUpdate,
)
from app.services.account_service import AccountService
from app.services.base import BaseService
from app.services.user_service import UserService
from app.utils.imagekit import build_imagekit_webp_url


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
        desserts = list(
            self.db.execute(
                select(Dessert).options(selectinload(Dessert.category))
            ).scalars().all()
        )
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

        return {
            "total_revenue": total_revenue,
            "total_orders": len(orders),
            "pending_orders": status_counts[OrderStatus.PENDING.value],
            "delivered_orders": status_counts[OrderStatus.DELIVERED.value],
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
        }

    def list_category_options(self) -> list[dict]:
        categories = list(
            self.db.execute(select(Category).order_by(Category.name.asc())).scalars().all()
        )
        return [
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "is_active": category.is_active,
            }
            for category in categories
        ]

    def list_categories(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        filters = []
        if search:
            query = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(
                    func.concat(
                        Category.name,
                        " ",
                        Category.slug,
                        " ",
                        func.coalesce(Category.description, ""),
                    )
                ).like(query)
            )
        if status == "active":
            filters.append(Category.is_active.is_(True))
        elif status == "hidden":
            filters.append(Category.is_active.is_(False))

        base_statement = select(Category).options(selectinload(Category.desserts))
        if filters:
            base_statement = base_statement.where(*filters)

        total = self._count_from_statement(base_statement)
        categories = list(
            self.db.execute(
                base_statement.order_by(Category.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        stats = self._build_category_stats()
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_category(category) for category in categories],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": stats,
        }

    def create_category(self, payload: AdminCategoryCreate) -> Category:
        slug = self._ensure_unique_slug(Category, payload.slug or payload.name)
        category = Category(
            name=payload.name.strip(),
            slug=slug,
            image=payload.image or None,
            description=payload.description or None,
            is_active=payload.is_active,
        )
        self.db.add(category)
        self.commit()
        return self.refresh(category)

    def update_category(self, category_id: UUID, payload: AdminCategoryUpdate) -> Category:
        category = self._get_category(category_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            category.name = data["name"].strip()
        if "slug" in data or ("name" in data and data.get("name")):
            category.slug = self._ensure_unique_slug(
                Category,
                data.get("slug") or data.get("name") or category.slug,
                exclude_id=category.id,
            )
        for field in ("image", "description", "is_active"):
            if field in data:
                setattr(category, field, data[field] or None if field in {"image", "description"} else data[field])
        self.db.add(category)
        self.commit()
        return self.refresh(category)

    def upload_image(self, image: UploadFile) -> tuple[str, str | None]:
        return UserService._upload_image(
            UserService,
            image,
            folder="/sweet-charm/general",
            width=1200,
            quality=82,
        )

    def upload_category_image(self, category_id: UUID, image: UploadFile) -> dict:
        category = self._get_category(category_id)
        uploaded_url, uploaded_file_id = UserService._upload_image(
            UserService,
            image,
            folder="/sweet-charm/categories",
            width=800,
            quality=82,
        )
        category.image = uploaded_url
        self.db.add(category)
        self.commit()
        return {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "image": category.image,
            "description": category.description,
            "is_active": category.is_active,
            "created_at": category.created_at,
            "desserts_count": len(category.desserts),
        }

    def delete_category(self, category_id: UUID) -> None:
        category = self._get_category(category_id)
        if category.desserts:
            raise self.bad_request("Category has desserts and cannot be deleted")
        self.db.delete(category)
        self.commit()

    def list_desserts(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
        category_id: UUID | None = None,
    ) -> dict:
        filters = []
        if search:
            query = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(
                    func.concat(
                        Dessert.name,
                        " ",
                        Dessert.slug,
                        " ",
                        func.coalesce(Dessert.description, ""),
                        " ",
                        func.coalesce(Category.name, ""),
                    )
                ).like(query)
            )
        if status and status != "all":
            filters.append(Dessert.status == status)
        if category_id:
            filters.append(Dessert.category_id == category_id)

        base_statement = (
            select(Dessert)
            .join(Category, Dessert.category_id == Category.id)
            .options(selectinload(Dessert.category), selectinload(Dessert.images))
        )
        if filters:
            base_statement = base_statement.where(*filters)

        total = self._count_from_statement(base_statement)
        desserts = list(
            self.db.execute(
                base_statement.order_by(Dessert.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        stats = self._build_dessert_stats()
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_dessert(dessert) for dessert in desserts],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": stats,
        }

    def create_dessert(self, payload: AdminDessertCreate) -> dict:
        self._get_category(payload.category_id)
        slug = self._ensure_unique_slug(Dessert, payload.slug or payload.name)
        dessert = Dessert(
            category_id=payload.category_id,
            name=payload.name.strip(),
            slug=slug,
            description=payload.description or None,
            ingredients=payload.ingredients or None,
            price=payload.price,
            old_price=payload.old_price,
            stock=payload.stock,
            status=payload.status,
            is_featured=payload.is_featured,
            is_best_seller=payload.is_best_seller,
        )
        self.db.add(dessert)
        self.db.flush()
        self._replace_dessert_images(dessert, payload.image_url, payload.image_urls)
        self.commit()
        self.db.refresh(dessert)
        return self._serialize_dessert(self._get_dessert(dessert.id))

    def update_dessert(self, dessert_id: UUID, payload: AdminDessertUpdate) -> dict:
        dessert = self._get_dessert(dessert_id)
        data = payload.model_dump(exclude_unset=True)
        if "category_id" in data and data["category_id"] is not None:
            self._get_category(data["category_id"])
            dessert.category_id = data["category_id"]
        if "name" in data and data["name"] is not None:
            dessert.name = data["name"].strip()
        if "slug" in data or ("name" in data and data.get("name")):
            dessert.slug = self._ensure_unique_slug(
                Dessert,
                data.get("slug") or data.get("name") or dessert.slug,
                exclude_id=dessert.id,
            )
        for field in (
            "description",
            "ingredients",
            "price",
            "old_price",
            "stock",
            "status",
            "is_featured",
            "is_best_seller",
        ):
            if field in data:
                setattr(dessert, field, data[field])
        if "image_url" in data or "image_urls" in data:
            self._replace_dessert_images(dessert, data.get("image_url"), data.get("image_urls") or [])
        self.db.add(dessert)
        self.commit()
        return self._serialize_dessert(self._get_dessert(dessert.id))

    def delete_dessert(self, dessert_id: UUID) -> None:
        dessert = self._get_dessert(dessert_id)
        self.db.delete(dessert)
        self.commit()

    def list_orders(
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

        stats = self._build_order_stats()
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": stats,
        }

    def update_order(self, order_id: UUID, payload: AdminOrderUpdate) -> Order:
        order = self._get_order(order_id)
        previous_status = order.status
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(order, field, value)
        if previous_status != OrderStatus.DELIVERED and order.status == OrderStatus.DELIVERED:
            AccountService(self.db).handle_order_delivered_rewards(order)
        self.db.add(order)
        self.commit()
        return self.refresh(order)

    def list_reviews(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        state: str | None = None,
    ) -> dict:
        filters = []
        if state == "approved":
            filters.append(Review.is_approved.is_(True))
        elif state == "pending":
            filters.append(Review.is_approved.is_(False))
            filters.append(Review.rating >= 3)
        elif state == "rejected":
            filters.append(Review.is_approved.is_(False))
            filters.append(Review.rating <= 2)
        if search:
            query = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(
                    func.concat(
                        func.coalesce(User.full_name, ""),
                        " ",
                        func.coalesce(User.email, ""),
                        " ",
                        func.coalesce(Dessert.name, ""),
                        " ",
                        func.coalesce(Review.text, ""),
                    )
                ).like(query)
            )

        base_statement = (
            select(Review)
            .join(User, Review.user_id == User.id)
            .join(Dessert, Review.dessert_id == Dessert.id)
            .options(selectinload(Review.user), selectinload(Review.dessert))
        )
        if filters:
            base_statement = base_statement.where(*filters)

        total = self._count_from_statement(base_statement)
        reviews = list(
            self.db.execute(
                base_statement.order_by(Review.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        stats = self._build_review_stats()
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_review(review) for review in reviews],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": stats,
        }

    def update_review(self, review_id: UUID, is_approved: bool) -> Review:
        review = self._get_review(review_id)
        review.is_approved = is_approved
        self.db.add(review)
        self.commit()
        self._refresh_dessert_rating(review.dessert_id)
        self.commit()
        return self.refresh(review)

    def delete_review(self, review_id: UUID) -> None:
        review = self._get_review(review_id)
        dessert_id = review.dessert_id
        self.db.delete(review)
        self.commit()
        self._refresh_dessert_rating(dessert_id)
        self.commit()

    def list_users(self) -> list[User]:
        return list(
            self.db.execute(
                select(User).where(User.role == UserRole.USER).order_by(User.created_at.desc())
            ).scalars().all()
        )

    def list_customers(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        filters = [User.role == UserRole.USER]
        if status == "active":
            filters.append(User.is_active.is_(True))
        elif status == "inactive":
            filters.append(User.is_active.is_(False))
        if search:
            query = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(
                    func.concat(
                        User.full_name,
                        " ",
                        User.email,
                        " ",
                        func.coalesce(User.phone, ""),
                    )
                ).like(query)
            )

        base_statement = (
            select(User)
            .options(selectinload(User.orders), selectinload(User.reviews))
            .where(*filters)
        )
        total = self._count_from_statement(base_statement)
        users = list(
            self.db.execute(
                base_statement.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_customer(user) for user in users],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_customer_stats(),
        }

    def create_admin_user(self, payload: AdminCreateUser) -> User:
        return UserService(self.db).create_admin(payload)

    def _get_category(self, category_id: UUID) -> Category:
        category = self.db.execute(
            select(Category).options(selectinload(Category.desserts)).where(Category.id == category_id)
        ).scalar_one_or_none()
        if not category:
            raise self.not_found("Category")
        return category

    def _get_dessert(self, dessert_id: UUID) -> Dessert:
        dessert = self.db.execute(
            select(Dessert)
            .options(selectinload(Dessert.category), selectinload(Dessert.images))
            .where(Dessert.id == dessert_id)
        ).scalar_one_or_none()
        if not dessert:
            raise self.not_found("Dessert")
        return dessert

    def _get_order(self, order_id: UUID) -> Order:
        order = self.db.execute(
            select(Order).options(selectinload(Order.items), selectinload(Order.user)).where(Order.id == order_id)
        ).scalar_one_or_none()
        if not order:
            raise self.not_found("Order")
        return order

    def _get_review(self, review_id: UUID) -> Review:
        review = self.db.execute(
            select(Review).options(selectinload(Review.user), selectinload(Review.dessert)).where(Review.id == review_id)
        ).scalar_one_or_none()
        if not review:
            raise self.not_found("Review")
        return review

    def _serialize_dessert(self, dessert: Dessert) -> dict:
        images = [image.image_url for image in dessert.images if image.image_url]
        main_image = next((image.image_url for image in dessert.images if image.is_main), None)
        return {
            "id": dessert.id,
            "category_id": dessert.category_id,
            "category_name": dessert.category.name if dessert.category else None,
            "name": dessert.name,
            "slug": dessert.slug,
            "description": dessert.description,
            "ingredients": dessert.ingredients,
            "price": dessert.price,
            "old_price": dessert.old_price,
            "stock": dessert.stock,
            "status": dessert.status,
            "is_featured": dessert.is_featured,
            "is_best_seller": dessert.is_best_seller,
            "rating_avg": dessert.rating_avg,
            "reviews_count": dessert.reviews_count,
            "image_url": main_image,
            "image_urls": images,
            "created_at": dessert.created_at,
            "updated_at": dessert.updated_at,
        }

    def _serialize_category(self, category: Category) -> dict:
        return {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "image": category.image,
            "description": category.description,
            "is_active": category.is_active,
            "created_at": category.created_at,
            "desserts_count": len(category.desserts),
        }

    def _serialize_review(self, review: Review) -> dict:
        return {
            "id": review.id,
            "dessert_id": review.dessert_id,
            "dessert_name": review.dessert.name if review.dessert else None,
            "user_id": review.user_id,
            "customer_name": review.user.full_name if review.user else "Customer",
            "customer_email": review.user.email if review.user else None,
            "avatar": review.user.avatar if review.user else None,
            "rating": review.rating,
            "text": review.text,
            "is_approved": review.is_approved,
            "created_at": review.created_at,
        }

    def _serialize_customer(self, user: User) -> dict:
        return {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "avatar": user.avatar,
            "role": user.role,
            "is_active": user.is_active,
            "birthday": user.birthday,
            "bio": user.bio,
            "orders_count": len(user.orders),
            "reviews_count": len(user.reviews),
            "created_at": user.created_at,
        }

    def _build_category_stats(self) -> dict:
        categories = list(self.db.execute(select(Category.is_active)).all())
        total = len(categories)
        active = sum(1 for (is_active,) in categories if is_active)
        return {"total": total, "active": active, "hidden": total - active}

    def _build_dessert_stats(self) -> dict:
        desserts = list(self.db.execute(select(Dessert.status, Dessert.stock)).all())
        total = len(desserts)
        active = sum(1 for status, _ in desserts if status == DessertStatus.ACTIVE)
        inactive = sum(1 for status, _ in desserts if status == DessertStatus.INACTIVE)
        out_of_stock = sum(
            1
            for status, stock in desserts
            if status == DessertStatus.OUT_OF_STOCK or stock <= 0
        )
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "out_of_stock": out_of_stock,
        }

    def _build_order_stats(self) -> dict:
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

    def _build_review_stats(self) -> dict:
        reviews = list(self.db.execute(select(Review.rating, Review.is_approved)).all())
        total = len(reviews)
        approved = sum(1 for _, is_approved in reviews if is_approved)
        rejected = sum(1 for rating, is_approved in reviews if not is_approved and rating <= 2)
        pending = sum(1 for rating, is_approved in reviews if not is_approved and rating >= 3)
        average_rating = round(sum(rating for rating, _ in reviews) / total, 1) if total else 0.0
        return {
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "average_rating": average_rating,
        }

    def _build_customer_stats(self) -> dict:
        users = list(
            self.db.execute(select(User.is_active, User.created_at).where(User.role == UserRole.USER)).all()
        )
        total = len(users)
        active = sum(1 for is_active, _ in users if is_active)
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = sum(1 for _, created_at in users if created_at >= month_start)
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "new_this_month": new_this_month,
        }

    def _count_from_statement(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _replace_dessert_images(self, dessert: Dessert, image_url: str | None, image_urls: list[str]) -> None:
        unique_urls: list[str] = []
        if image_url:
            unique_urls.append(image_url)
        for url in image_urls:
            if url and url not in unique_urls:
                unique_urls.append(url)

        dessert.images.clear()
        self.db.flush()

        dessert.images.extend(
            DessertImage(
                dessert_id=dessert.id,
                image_url=url,
                is_main=index == 0,
            )
            for index, url in enumerate(unique_urls)
        )
        self.db.flush()

    def _refresh_dessert_rating(self, dessert_id: UUID) -> None:
        dessert = self.db.get(Dessert, dessert_id)
        if not dessert:
            return

        approved_reviews = list(
            self.db.execute(
                select(Review).where(Review.dessert_id == dessert_id, Review.is_approved.is_(True))
            ).scalars().all()
        )
        dessert.reviews_count = len(approved_reviews)
        if approved_reviews:
            total = sum(review.rating for review in approved_reviews)
            dessert.rating_avg = Decimal(total / len(approved_reviews)).quantize(Decimal("0.01"))
        else:
            dessert.rating_avg = Decimal("0")
        self.db.add(dessert)

    @staticmethod
    def _build_weekly_revenue_series(orders: list[Order], now: datetime) -> list[dict]:
        points: list[dict] = []
        for offset in range(7, -1, -1):
            week_start = (now - timedelta(days=offset * 7)).date()
            week_end = week_start + timedelta(days=6)
            week_orders = [order for order in orders if week_start <= order.created_at.date() <= week_end]
            points.append(
                {
                    "label": f"{week_start.strftime('%d %b')}",
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

    def _ensure_unique_slug(self, model, value: str, exclude_id: UUID | None = None) -> str:
        slug = self._slugify(value)
        if not slug:
            slug = "item"
        candidate = slug
        counter = 2
        while True:
            statement = select(model).where(model.slug == candidate)
            existing = self.db.execute(statement).scalar_one_or_none()
            if not existing or (exclude_id and existing.id == exclude_id):
                return candidate
            candidate = f"{slug}-{counter}"
            counter += 1

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
        return normalized.strip("-")

    @staticmethod
    def _shift_month(base: datetime, months_delta: int) -> datetime:
        month_index = (base.month - 1) + months_delta
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        return base.replace(year=year, month=month, day=1)


def get_admin_service(db: Session) -> AdminService:
    return AdminService(db)
