from app.routers.admin_router import router as admin_router
from app.routers.account_router import router as account_router
from app.routers.auth_router import router as auth_router
from app.routers.birthday_greeting_router import router as birthday_greeting_router
from app.routers.category_router import router as category_router
from app.routers.coupon_router import router as coupon_router
from app.routers.dessert_router import router as dessert_router
from app.routers.gallery_image_router import router as gallery_image_router
from app.routers.order_router import router as order_router
from app.routers.realtime_router import router as realtime_router
from app.routers.review_router import router as review_router
from app.routers.upload_router import router as upload_router
from app.routers.user_router import router as user_router

__all__ = [
    "admin_router",
    "account_router",
    "auth_router",
    "birthday_greeting_router",
    "category_router",
    "coupon_router",
    "dessert_router",
    "gallery_image_router",
    "order_router",
    "realtime_router",
    "review_router",
    "upload_router",
    "user_router",
]
