from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.dessert import Dessert
from app.models.enums import DessertStatus
from app.models.review import Review
from app.services.base import BaseService


class DessertService(BaseService):
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

    def list_categories(self) -> list[str]:
        statement = select(Category.name).where(Category.is_active.is_(True)).order_by(Category.name.asc())
        return list(self.db.execute(statement).scalars().all())

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


def get_dessert_service(db: Session) -> DessertService:
    return DessertService(db)
