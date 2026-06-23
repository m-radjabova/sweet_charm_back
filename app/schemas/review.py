from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class FeaturedReviewOut(ORMModel):
    id: UUID
    customer_name: str
    rating: int
    text: str
    created_at: datetime
    dessert_name: str | None = None


class DessertReviewOut(ORMModel):
    id: UUID
    customer_name: str
    rating: int
    text: str
    created_at: datetime
    avatar: str | None = None
    is_mine: bool = False


class ReviewCreate(ORMModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=1200)
