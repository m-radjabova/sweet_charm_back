from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.dessert import Dessert
from app.models.dessert_image import DessertImage
from app.models.enums import DessertStatus
from app.models.review import Review
from app.schemas.admin import AdminDessertCreate, AdminDessertUpdate
from app.schemas.dessert import FeaturedDessertOut
from app.realtime import realtime_manager
from app.services.base import BaseService
from app.services.user_service import UserService


class DessertService(BaseService):
    LOW_STOCK_THRESHOLD = 4

    def list_all(
        self,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        dietary: str | None = None,
        min_rating: float | None = None,
        search: str | None = None,
    ) -> list[dict]:
        statement = (
            select(Dessert)
            .join(Dessert.category)
            .where(
                Dessert.status == DessertStatus.ACTIVE,
                Category.is_active.is_(True),
            )
            .options(
                selectinload(Dessert.images),
                selectinload(Dessert.category),
                selectinload(Dessert.reviews),
            )
            .order_by(
                Dessert.is_best_seller.desc(),
                Dessert.rating_avg.desc(),
                Dessert.created_at.desc(),
            )
        )

        if category:
            statement = statement.where(Category.name == category)
        if min_price is not None:
            statement = statement.where(Dessert.price >= min_price)
        if max_price is not None:
            statement = statement.where(Dessert.price <= max_price)
        if dietary:
            dietary_term = f"%{dietary.strip()}%"
            statement = statement.where(
                or_(
                    Dessert.name.ilike(dietary_term),
                    Dessert.description.ilike(dietary_term),
                    Dessert.ingredients.ilike(dietary_term),
                )
            )
        if min_rating is not None:
            statement = statement.where(Dessert.rating_avg >= min_rating)
        if search:
            search_term = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    Dessert.name.ilike(search_term),
                    Dessert.description.ilike(search_term),
                    Category.name.ilike(search_term),
                )
            )

        desserts = self.db.execute(statement).scalars().all()
        return [self._serialize_dessert(dessert) for dessert in desserts]

    def list_best_sellers(self, limit: int = 6) -> list[dict]:
        statement = (
            select(Dessert)
            .where(
                Dessert.is_best_seller.is_(True),
                Dessert.status == DessertStatus.ACTIVE,
            )
            .options(
                selectinload(Dessert.images),
                selectinload(Dessert.category),
                selectinload(Dessert.reviews),
            )
            .order_by(
                Dessert.rating_avg.desc(),
                Dessert.created_at.desc(),
            )
            .limit(limit)
        )

        desserts = self.db.execute(statement).scalars().all()
        return [self._serialize_dessert(dessert) for dessert in desserts]

    def list_featured(self, limit: int = 8) -> list[dict]:
        statement = (
            select(Dessert)
            .where(
                Dessert.is_featured.is_(True),
                Dessert.status == DessertStatus.ACTIVE,
            )
            .options(
                selectinload(Dessert.images),
                selectinload(Dessert.category),
                selectinload(Dessert.reviews),
            )
            .order_by(
                Dessert.created_at.desc(),
                Dessert.is_best_seller.desc(),
                Dessert.rating_avg.desc(),
            )
            .limit(limit)
        )

        desserts = self.db.execute(statement).scalars().all()
        return [self._serialize_dessert(dessert) for dessert in desserts]

    def get_chef_choice(self) -> dict | None:
        statement = (
            select(Dessert)
            .where(
                Dessert.is_chef_choice.is_(True),
                Dessert.status == DessertStatus.ACTIVE,
            )
            .options(
                selectinload(Dessert.images),
                selectinload(Dessert.category),
                selectinload(Dessert.reviews),
            )
            .order_by(Dessert.updated_at.desc(), Dessert.created_at.desc())
            .limit(1)
        )
        dessert = self.db.execute(statement).scalar_one_or_none()
        return self._serialize_dessert(dessert) if dessert else None

    def list_categories(self) -> list[str]:
        statement = select(Category.name).where(Category.is_active.is_(True)).order_by(Category.name.asc())
        return list(self.db.execute(statement).scalars().all())

    def list_admin(
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
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_admin_dessert(dessert) for dessert in desserts],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_admin_stats(),
        }

    def create_admin(self, payload: AdminDessertCreate) -> dict:
        self._get_category(payload.category_id)
        slug = self._ensure_unique_slug(payload.slug or payload.name)
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
            is_chef_choice=payload.is_chef_choice,
        )
        self.db.add(dessert)
        self.db.flush()
        if payload.is_chef_choice:
            self._clear_other_chef_choices(dessert.id)
        self._replace_images(dessert, payload.image_url, payload.image_urls)
        self.commit()
        refreshed = self._get_admin_dessert(dessert.id)
        self._emit_stock_update([refreshed])
        self._emit_chef_choice_update()
        return self._serialize_admin_dessert(refreshed)

    def update_admin(self, dessert_id: UUID, payload: AdminDessertUpdate) -> dict:
        dessert = self._get_admin_dessert(dessert_id)
        data = payload.model_dump(exclude_unset=True)
        if "category_id" in data and data["category_id"] is not None:
            self._get_category(data["category_id"])
            dessert.category_id = data["category_id"]
        if "name" in data and data["name"] is not None:
            dessert.name = data["name"].strip()
        if "slug" in data or ("name" in data and data.get("name")):
            dessert.slug = self._ensure_unique_slug(
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
            "is_chef_choice",
        ):
            if field in data:
                setattr(dessert, field, data[field])
        if data.get("is_chef_choice") is True:
            self._clear_other_chef_choices(dessert.id)
        if "image_url" in data or "image_urls" in data:
            self._replace_images(dessert, data.get("image_url"), data.get("image_urls") or [])
        self.db.add(dessert)
        self.commit()
        refreshed = self._get_admin_dessert(dessert.id)
        self._emit_stock_update([refreshed])
        self._emit_chef_choice_update()
        return self._serialize_admin_dessert(refreshed)

    def delete_admin(self, dessert_id: UUID) -> None:
        dessert = self._get_admin_dessert(dessert_id)
        should_emit_chef_choice = dessert.is_chef_choice
        self.db.delete(dessert)
        self.commit()
        if should_emit_chef_choice:
            self._emit_chef_choice_update()

    def upload_image(self, image: UploadFile) -> tuple[str, str | None]:
        return UserService._upload_image(
            UserService,
            image,
            folder="/sweet-charm/general",
            width=1200,
            quality=82,
        )

    def _serialize_dessert(self, dessert: Dessert) -> dict:
        return {
            "id": str(dessert.id),
            "name": dessert.name,
            "slug": dessert.slug,
            "description": dessert.description,
            "ingredients": dessert.ingredients,
            "price": dessert.price,
            "old_price": dessert.old_price,
            "image_url": next((image.image_url for image in dessert.images if image.is_main), None),
            "image_urls": [image.image_url for image in dessert.images if image.image_url],
            "rating_avg": self._calculate_rating_avg(dessert.reviews),
            "reviews_count": self._calculate_reviews_count(dessert.reviews),
            "category_name": dessert.category.name if dessert.category else None,
            "stock": dessert.stock,
            "status": dessert.status,
            "is_chef_choice": dessert.is_chef_choice,
        }

    def _serialize_admin_dessert(self, dessert: Dessert) -> dict:
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
            "is_chef_choice": dessert.is_chef_choice,
            "rating_avg": dessert.rating_avg,
            "reviews_count": dessert.reviews_count,
            "image_url": main_image,
            "image_urls": images,
            "created_at": dessert.created_at,
            "updated_at": dessert.updated_at,
        }

    @staticmethod
    def _approved_reviews(reviews: list[Review]) -> list[Review]:
        return [review for review in reviews if review.is_approved]

    def _calculate_reviews_count(self, reviews: list[Review]) -> int:
        return len(self._approved_reviews(reviews))

    def _calculate_rating_avg(self, reviews: list[Review]) -> float:
        approved_reviews = self._approved_reviews(reviews)
        if not approved_reviews:
            return 0.0

        total = sum(review.rating for review in approved_reviews)
        avg = Decimal(total) / Decimal(len(approved_reviews))
        return float(avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _get_category(self, category_id: UUID) -> Category:
        category = self.db.execute(
            select(Category).options(selectinload(Category.desserts)).where(Category.id == category_id)
        ).scalar_one_or_none()
        if not category:
            raise self.not_found("Category")
        return category

    def _get_admin_dessert(self, dessert_id: UUID) -> Dessert:
        dessert = self.db.execute(
            select(Dessert)
            .options(selectinload(Dessert.category), selectinload(Dessert.images))
            .where(Dessert.id == dessert_id)
        ).scalar_one_or_none()
        if not dessert:
            raise self.not_found("Dessert")
        return dessert

    def _replace_images(self, dessert: Dessert, image_url: str | None, image_urls: list[str]) -> None:
        unique_urls: list[str] = []
        if image_url:
            unique_urls.append(image_url)
        for url in image_urls:
            if url and url not in unique_urls:
                unique_urls.append(url)

        dessert.images.clear()
        self.db.flush()
        dessert.images.extend(
            DessertImage(dessert_id=dessert.id, image_url=url, is_main=index == 0)
            for index, url in enumerate(unique_urls)
        )
        self.db.flush()

    def _clear_other_chef_choices(self, dessert_id: UUID) -> None:
        self.db.execute(
            update(Dessert)
            .where(Dessert.id != dessert_id, Dessert.is_chef_choice.is_(True))
            .values(is_chef_choice=False)
        )
        self.db.flush()

    def _build_admin_stats(self) -> dict:
        desserts = list(self.db.execute(select(Dessert.status, Dessert.stock)).all())
        total = len(desserts)
        active = sum(1 for status, _ in desserts if status == DessertStatus.ACTIVE)
        inactive = sum(1 for status, _ in desserts if status == DessertStatus.INACTIVE)
        out_of_stock = sum(1 for status, stock in desserts if status == DessertStatus.OUT_OF_STOCK or stock <= 0)
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "out_of_stock": out_of_stock,
        }

    def _count_from_statement(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())

    def _ensure_unique_slug(self, value: str, exclude_id: UUID | None = None) -> str:
        slug = self._slugify(value)
        if not slug:
            slug = "item"
        candidate = slug
        counter = 2
        while True:
            statement = select(Dessert).where(Dessert.slug == candidate)
            existing = self.db.execute(statement).scalar_one_or_none()
            if not existing or (exclude_id and existing.id == exclude_id):
                return candidate
            candidate = f"{slug}-{counter}"
            counter += 1

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
        return normalized.strip("-")

    def serialize_stock_item(self, dessert: Dessert) -> dict:
        public_payload = FeaturedDessertOut.model_validate(self._serialize_dessert(dessert))
        stock = max(0, int(dessert.stock or 0))
        status = DessertStatus.OUT_OF_STOCK if stock <= 0 else dessert.status
        return {
            "dessert_id": str(dessert.id),
            "slug": dessert.slug,
            "name": dessert.name,
            "stock": stock,
            "status": status.value if isinstance(status, DessertStatus) else str(status),
            "is_low_stock": 0 < stock <= self.LOW_STOCK_THRESHOLD,
            "is_out_of_stock": stock <= 0,
            "dessert": jsonable_encoder(public_payload),
        }

    def _emit_stock_update(self, desserts: list[Dessert]) -> None:
        if not desserts:
            return

        payload_items = [self.serialize_stock_item(dessert) for dessert in desserts]
        realtime_manager.emit_to_admins_sync("stock_updated", {"items": payload_items})
        realtime_manager.emit_to_role_sync("user", "stock_updated", {"items": payload_items})

        alert_items = [item for item in payload_items if item["is_low_stock"] or item["is_out_of_stock"]]
        if not alert_items:
            return

        realtime_manager.emit_to_admins_sync("low_stock_alert", {"items": alert_items})
        for item in alert_items:
            stock = int(item["stock"])
            title = "Out of stock" if item["is_out_of_stock"] else "Low stock alert"
            message = (
                f"{item['name']} is now out of stock."
                if item["is_out_of_stock"]
                else f"{item['name']} stock is down to {stock}."
            )
            realtime_manager.emit_to_admins_sync(
                "notification_created",
                {
                    "id": f"stock-{item['dessert_id']}-{stock}",
                    "kind": "low_stock" if item["is_low_stock"] else "out_of_stock",
                    "title": title,
                    "message": message,
                    "metadata": item,
                },
            )

    def _emit_chef_choice_update(self) -> None:
        payload = self.get_chef_choice()
        realtime_manager.emit_to_admins_sync("chef_choice_updated", {"dessert": payload})
        realtime_manager.emit_to_role_sync("user", "chef_choice_updated", {"dessert": payload})


def get_dessert_service(db: Session) -> DessertService:
    return DessertService(db)
