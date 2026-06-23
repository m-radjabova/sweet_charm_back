from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.database import engine
from app.core.config import settings
from app.models.coupon import Coupon
from app.routers import (
    admin_router,
    account_router,
    auth_router,
    category_router,
    coupon_router,
    dessert_router,
    gallery_image_router,
    order_router,
    review_router,
    upload_router,
    user_router,
)


app = FastAPI(title="Sweet Charm API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(account_router)
app.include_router(category_router)
app.include_router(coupon_router)
app.include_router(dessert_router)
app.include_router(gallery_image_router)
app.include_router(order_router)
app.include_router(review_router)
app.include_router(upload_router)
app.include_router(user_router)


@app.on_event("startup")
def ensure_profile_schema() -> None:
    Coupon.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE addresses ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"))
        connection.execute(text("ALTER TABLE addresses ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_file_id VARCHAR(255)"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS sweet_points INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS usage_limit INTEGER"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS assigned_user_id UUID"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS reward_tier VARCHAR(32)"))
        connection.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(64)"))
        connection.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_coupons_assigned_user_id ON coupons (assigned_user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_coupons_reward_tier ON coupons (reward_tier)"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS point_transactions (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    order_id UUID NULL REFERENCES orders(id) ON DELETE SET NULL,
                    points INTEGER NOT NULL,
                    type VARCHAR(32) NOT NULL,
                    description TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_point_transactions_user_id ON point_transactions (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_point_transactions_order_id ON point_transactions (order_id)"))


@app.get("/health", tags=["Health"])
def healthcheck():
    return {"status": "ok"}
