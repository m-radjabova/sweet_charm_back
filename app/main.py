from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.database import engine
from app.core.config import settings
from app.models.coupon import Coupon
from app.models.birthday_greeting import BirthdayGreeting
from app.models.gallery_image import GalleryImage
from app.models.reward_coupon import RewardCoupon
from app.routers import (
    admin_router,
    account_router,
    auth_router,
    birthday_greeting_router,
    category_router,
    coupon_router,
    dessert_router,
    gallery_image_router,
    order_router,
    realtime_router,
    review_router,
    upload_router,
    user_router,
)


app = FastAPI(title="Sweet Charm API ", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(birthday_greeting_router)
app.include_router(admin_router)
app.include_router(account_router)
app.include_router(category_router)
app.include_router(coupon_router)
app.include_router(dessert_router)
app.include_router(gallery_image_router)
app.include_router(order_router)
app.include_router(realtime_router)
app.include_router(review_router)
app.include_router(upload_router)
app.include_router(user_router)


@app.on_event("startup")
def ensure_profile_schema() -> None:
    Coupon.__table__.create(bind=engine, checkfirst=True)
    BirthdayGreeting.__table__.create(bind=engine, checkfirst=True)
    GalleryImage.__table__.create(bind=engine, checkfirst=True)
    RewardCoupon.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE addresses ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"))
        connection.execute(text("ALTER TABLE addresses ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_file_id VARCHAR(255)"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS sweet_points INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_level VARCHAR(32) NOT NULL DEFAULT 'bronze'"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS usage_limit INTEGER"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS assigned_user_id UUID"))
        connection.execute(text("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS reward_tier VARCHAR(32)"))
        connection.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(64)"))
        connection.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE desserts ADD COLUMN IF NOT EXISTS is_chef_choice BOOLEAN NOT NULL DEFAULT FALSE"))
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
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_rewards (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reward_type VARCHAR(64) NOT NULL,
                    threshold_points INTEGER NOT NULL,
                    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_user_rewards_user_reward_threshold
                ON user_rewards (user_id, reward_type, threshold_points)
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_rewards_user_id ON user_rewards (user_id)"))
        connection.execute(
            text(
                """
                INSERT INTO reward_coupons (
                    id, user_id, code, type, value, minimum_order, reward_type, threshold_points,
                    status, issued_at, expires_at, created_at, updated_at
                )
                SELECT
                    c.id,
                    c.assigned_user_id,
                    c.code,
                    c.type,
                    c.value,
                    c.minimum_order,
                    COALESCE(c.reward_tier, 'legacy_reward'),
                    COALESCE(
                        CASE
                            WHEN c.reward_tier = 'silver' THEN 1000
                            WHEN c.reward_tier = 'gold' THEN 2500
                            WHEN c.reward_tier = 'diamond' THEN 5000
                            ELSE 5000
                        END,
                        5000
                    ),
                    c.status,
                    c.created_at,
                    c.end_date,
                    c.created_at,
                    c.updated_at
                FROM coupons c
                WHERE c.assigned_user_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM reward_coupons rc WHERE rc.code = c.code
                  )
                """
            )
        )
        connection.execute(text("DELETE FROM coupons WHERE assigned_user_id IS NOT NULL"))


@app.get("/health", tags=["Health"])
def healthcheck():
    return {"status": "ok"}
