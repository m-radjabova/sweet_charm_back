from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.dessert import Dessert
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewCreate
from app.services.base import BaseService


class ReviewService(BaseService):
    def list_featured(self, limit: int = 6) -> list[dict]:
        statement = (
            select(Review)
            .where(
                Review.is_approved.is_(True),
                Review.text.is_not(None),
            )
            .options(
                selectinload(Review.user),
                selectinload(Review.dessert),
            )
            .order_by(Review.created_at.asc())
            .limit(limit)
        )

        reviews = self.db.execute(statement).scalars().all()
        return [
            {
                "id": str(review.id),
                "customer_name": review.user.full_name if review.user else "SweetCharm customer",
                "rating": review.rating,
                "text": review.text or "",
                "created_at": review.created_at,
                "dessert_name": review.dessert.name if review.dessert else None,
            }
            for review in reviews
        ]

    def list_for_dessert(self, dessert_slug: str, current_user: User | None = None) -> list[dict]:
        dessert = self._get_dessert_by_slug(dessert_slug)
        statement = (
            select(Review)
            .where(
                Review.dessert_id == dessert.id,
                Review.is_approved.is_(True),
                Review.text.is_not(None),
            )
            .options(selectinload(Review.user))
            .order_by(Review.created_at.desc())
        )
        reviews = self.db.execute(statement).scalars().all()

        return [
            {
                "id": str(review.id),
                "customer_name": review.user.full_name if review.user else "SweetCharm customer",
                "rating": review.rating,
                "text": review.text or "",
                "created_at": review.created_at,
                "avatar": review.user.avatar if review.user else None,
                "is_mine": bool(current_user and review.user_id == current_user.id),
            }
            for review in reviews
        ]

    def create_for_dessert(self, dessert_slug: str, current_user: User, payload: ReviewCreate) -> dict:
        dessert = self._get_dessert_by_slug(dessert_slug)

        existing_review = self.db.execute(
            select(Review).where(
                Review.dessert_id == dessert.id,
                Review.user_id == current_user.id,
            )
        ).scalar_one_or_none()
        if existing_review:
            raise self.bad_request("Siz bu dessert uchun allaqachon review yozgansiz")

        review = Review(
            user_id=current_user.id,
            dessert_id=dessert.id,
            rating=payload.rating,
            text=payload.text.strip(),
            is_approved=False,
        )
        self.db.add(review)
        self.commit()
        self.db.refresh(review)

        return {
            "id": str(review.id),
            "customer_name": current_user.full_name,
            "rating": review.rating,
            "text": review.text or "",
            "created_at": review.created_at,
            "avatar": current_user.avatar,
            "is_mine": True,
        }

    def _get_dessert_by_slug(self, slug: str) -> Dessert:
        dessert = self.db.execute(select(Dessert).where(Dessert.slug == slug.strip())).scalar_one_or_none()
        if not dessert:
            raise self.not_found("Dessert")
        return dessert

    def _refresh_dessert_rating(self, dessert: Dessert) -> None:
        approved_reviews = self.db.execute(
            select(Review).where(
                Review.dessert_id == dessert.id,
                Review.is_approved.is_(True),
            )
        ).scalars().all()

        dessert.reviews_count = len(approved_reviews)
        if approved_reviews:
            avg = Decimal(sum(review.rating for review in approved_reviews)) / Decimal(len(approved_reviews))
            dessert.rating_avg = avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            dessert.rating_avg = Decimal("0")

        self.db.add(dessert)


def get_review_service(db: Session) -> ReviewService:
    return ReviewService(db)
