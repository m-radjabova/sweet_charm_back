from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gallery_image import GalleryImage
from app.services.base import BaseService


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


def get_gallery_image_service(db: Session) -> GalleryImageService:
    return GalleryImageService(db)
