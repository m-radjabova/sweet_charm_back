from datetime import datetime
from uuid import UUID

from app.schemas.common import ORMModel


class GalleryImageOut(ORMModel):
    id: UUID
    title: str | None = None
    image_url: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
