from __future__ import annotations

import re
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.schemas.admin import AdminCategoryCreate, AdminCategoryUpdate
from app.services.base import BaseService
from app.services.user_service import UserService


class CategoryService(BaseService):
    def list_options(self) -> list[dict]:
        categories = list(self.db.execute(select(Category).order_by(Category.name.asc())).scalars().all())
        return [
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "is_active": category.is_active,
            }
            for category in categories
        ]

    def list_admin(
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
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize(category) for category in categories],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_stats(),
        }

    def create(self, payload: AdminCategoryCreate) -> Category:
        slug = self._ensure_unique_slug(payload.slug or payload.name)
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

    def update(self, category_id: UUID, payload: AdminCategoryUpdate) -> Category:
        category = self._get(category_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            category.name = data["name"].strip()
        if "slug" in data or ("name" in data and data.get("name")):
            category.slug = self._ensure_unique_slug(
                data.get("slug") or data.get("name") or category.slug,
                exclude_id=category.id,
            )
        for field in ("image", "description", "is_active"):
            if field in data:
                setattr(category, field, data[field] or None if field in {"image", "description"} else data[field])
        self.db.add(category)
        self.commit()
        return self.refresh(category)

    def upload_image(self, category_id: UUID, image: UploadFile) -> dict:
        category = self._get(category_id)
        uploaded_url, _uploaded_file_id = UserService._upload_image(
            UserService,
            image,
            folder="/sweet-charm/categories",
            width=800,
            quality=82,
        )
        category.image = uploaded_url
        self.db.add(category)
        self.commit()
        return self._serialize(self.refresh(category))

    def delete(self, category_id: UUID) -> None:
        category = self._get(category_id)
        if category.desserts:
            raise self.bad_request("Category has desserts and cannot be deleted")
        self.db.delete(category)
        self.commit()

    def _get(self, category_id: UUID) -> Category:
        category = self.db.execute(
            select(Category).options(selectinload(Category.desserts)).where(Category.id == category_id)
        ).scalar_one_or_none()
        if not category:
            raise self.not_found("Category")
        return category

    def _serialize(self, category: Category) -> dict:
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

    def _build_stats(self) -> dict:
        categories = list(self.db.execute(select(Category.is_active)).all())
        total = len(categories)
        active = sum(1 for (is_active,) in categories if is_active)
        return {"total": total, "active": active, "hidden": total - active}

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
            statement = select(Category).where(Category.slug == candidate)
            existing = self.db.execute(statement).scalar_one_or_none()
            if not existing or (exclude_id and existing.id == exclude_id):
                return candidate
            candidate = f"{slug}-{counter}"
            counter += 1

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
        return normalized.strip("-")


def get_category_service(db: Session) -> CategoryService:
    return CategoryService(db)
