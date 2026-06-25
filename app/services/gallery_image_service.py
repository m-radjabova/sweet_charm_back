from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.gallery_image import GalleryImage
from app.schemas.admin import AdminGalleryImageCreate, AdminGalleryImageUpdate
from app.services.base import BaseService
from app.services.user_service import UserService


class GalleryImageService(BaseService):
    def list_active(self, limit: int = 7) -> list[GalleryImage]:
        statement = (
            select(GalleryImage)
            .where(GalleryImage.is_active.is_(True))
            .order_by(
                GalleryImage.sort_order.asc(),
                GalleryImage.created_at.asc(),
            )
            .limit(limit)
        )
        return self.db.execute(statement).scalars().all()

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
                        func.coalesce(GalleryImage.title, ""),
                        " ",
                        GalleryImage.image_url,
                    )
                ).like(query)
            )
        if status == "active":
            filters.append(GalleryImage.is_active.is_(True))
        elif status == "hidden":
            filters.append(GalleryImage.is_active.is_(False))

        base_statement = select(GalleryImage)
        if filters:
            base_statement = base_statement.where(*filters)

        total = self.db.execute(
            select(func.count()).select_from(base_statement.order_by(None).subquery())
        ).scalar_one()
        items = list(
            self.db.execute(
                base_statement.order_by(GalleryImage.sort_order.asc(), GalleryImage.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_stats(),
        }

    def create(self, payload: AdminGalleryImageCreate) -> GalleryImage:
        item = GalleryImage(
            title=payload.title or None,
            image_url=payload.image_url,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        self.db.add(item)
        self.commit()
        return self.refresh(item)

    def update(self, image_id: UUID, payload: AdminGalleryImageUpdate) -> GalleryImage:
        item = self._get(image_id)
        data = payload.model_dump(exclude_unset=True)
        for field in ("sort_order", "is_active"):
            if field in data:
                setattr(item, field, data[field])
        for field in ("title", "image_url"):
            if field in data:
                setattr(item, field, data[field] or None if field == "title" else data[field])
        self.db.add(item)
        self.commit()
        return self.refresh(item)

    def delete(self, image_id: UUID) -> None:
        item = self._get(image_id)
        self.db.delete(item)
        self.commit()

    def upload_image(self, image: UploadFile) -> tuple[str, str | None]:
        return UserService._upload_image(
            UserService,
            image,
            folder="/sweet-charm/gallery",
            width=1600,
            quality=84,
        )

    def _get(self, image_id: UUID) -> GalleryImage:
        item = self.db.execute(select(GalleryImage).where(GalleryImage.id == image_id)).scalar_one_or_none()
        if not item:
            raise self.not_found("Gallery image")
        return item

    def _serialize(self, item: GalleryImage) -> dict:
        return {
            "id": item.id,
            "title": item.title,
            "image_url": item.image_url,
            "sort_order": item.sort_order,
            "is_active": item.is_active,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _build_stats(self) -> dict:
        rows = list(self.db.execute(select(GalleryImage.is_active)).all())
        total = len(rows)
        active = sum(1 for (is_active,) in rows if is_active)
        return {"total": total, "active": active, "hidden": total - active}


def get_gallery_image_service(db: Session) -> GalleryImageService:
    return GalleryImageService(db)
