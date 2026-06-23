from decimal import Decimal

from pydantic import Field

from app.schemas.common import ORMModel


class FeaturedDessertOut(ORMModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    ingredients: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    rating_avg: float = 0
    reviews_count: int = 0
    category_name: str | None = Field(default=None)
