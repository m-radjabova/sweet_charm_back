from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.dessert import Dessert
from app.models.review import Review
from app.models.user import User
from app.schemas.admin import AdminReviewOut
from app.schemas.review import ReviewCreate
from app.realtime import realtime_manager
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
        admin_review = self._serialize_admin_review(self._get_admin_review(review.id))
        realtime_manager.emit_to_admins_sync(
            "new_review",
            {
                "review_id": str(review.id),
                "review": jsonable_encoder(AdminReviewOut.model_validate(admin_review)),
            },
        )
        realtime_manager.emit_to_admins_sync(
            "notification_created",
            {
                "id": f"new-review-{review.id}",
                "kind": "new_review",
                "title": "New review pending",
                "message": f"{current_user.full_name} submitted a review for {dessert.name}.",
                "metadata": {
                    "review_id": str(review.id),
                    "dessert_id": str(dessert.id),
                    "dessert_name": dessert.name,
                    "rating": review.rating,
                },
            },
        )

        return {
            "id": str(review.id),
            "customer_name": current_user.full_name,
            "rating": review.rating,
            "text": review.text or "",
            "created_at": review.created_at,
            "avatar": current_user.avatar,
            "is_mine": True,
        }

    def list_admin(
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
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [self._serialize_admin_review(review) for review in reviews],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": self._build_admin_stats(),
        }

    def update_admin(self, review_id: UUID, is_approved: bool) -> dict:
        review = self._get_admin_review(review_id)
        review.is_approved = is_approved
        self.db.add(review)
        self.commit()
        self._refresh_dessert_rating_by_id(review.dessert_id)
        self.commit()
        updated_review = self._serialize_admin_review(self._get_admin_review(review_id))
        payload = {
            "review_id": str(review_id),
            "review": jsonable_encoder(AdminReviewOut.model_validate(updated_review)),
            "is_approved": is_approved,
        }
        realtime_manager.emit_to_admins_sync("review_status_updated", payload)
        realtime_manager.emit_to_role_sync("user", "review_status_updated", payload)
        return updated_review

    def delete_admin(self, review_id: UUID) -> None:
        review = self._get_admin_review(review_id)
        dessert_id = review.dessert_id
        self.db.delete(review)
        self.commit()
        self._refresh_dessert_rating_by_id(dessert_id)
        self.commit()

    def _get_dessert_by_slug(self, slug: str) -> Dessert:
        dessert = self.db.execute(select(Dessert).where(Dessert.slug == slug.strip())).scalar_one_or_none()
        if not dessert:
            raise self.not_found("Dessert")
        return dessert

    def _get_admin_review(self, review_id: UUID) -> Review:
        review = self.db.execute(
            select(Review).options(selectinload(Review.user), selectinload(Review.dessert)).where(Review.id == review_id)
        ).scalar_one_or_none()
        if not review:
            raise self.not_found("Review")
        return review

    def _serialize_admin_review(self, review: Review) -> dict:
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

    def _refresh_dessert_rating_by_id(self, dessert_id: UUID) -> None:
        dessert = self.db.get(Dessert, dessert_id)
        if not dessert:
            return
        self._refresh_dessert_rating(dessert)

    def _build_admin_stats(self) -> dict:
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

    def _count_from_statement(self, statement) -> int:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        return int(self.db.execute(count_statement).scalar_one())


def get_review_service(db: Session) -> ReviewService:
    return ReviewService(db)
