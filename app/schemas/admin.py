from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.enums import DessertStatus, OrderStatus, PaymentMethod, PaymentStatus, UserRole
from app.schemas.common import ORMModel, validate_app_email


class AdminMetricPoint(ORMModel):
    label: str
    value: float


class AdminSeriesGroup(ORMModel):
    daily: list[AdminMetricPoint]
    weekly: list[AdminMetricPoint]
    monthly: list[AdminMetricPoint]


class AdminBreakdownItem(ORMModel):
    key: str
    label: str
    value: int


class AdminTopDessertItem(ORMModel):
    dessert_id: UUID | None = None
    dessert_name: str
    orders_count: int
    revenue: Decimal


class AdminRecentOrderItem(ORMModel):
    id: UUID
    customer_name: str
    total_price: Decimal
    status: OrderStatus
    created_at: datetime


class AdminLowStockItem(ORMModel):
    id: UUID
    name: str
    slug: str
    stock: int
    status: DessertStatus
    category_name: str | None = None


class AdminHeatmapCell(ORMModel):
    time: str
    value: int


class AdminHeatmapRow(ORMModel):
    day: str
    slots: list[AdminHeatmapCell]


class AdminDashboardOut(ORMModel):
    total_revenue: Decimal
    total_orders: int
    pending_orders: int
    delivered_orders: int
    low_stock_count: int
    pending_reviews: int
    approved_reviews: int
    total_desserts: int
    total_categories: int
    active_users: int
    average_rating: float
    sales_overview: AdminSeriesGroup
    new_customers_growth: AdminSeriesGroup
    orders_timeline: list[AdminMetricPoint]
    revenue_timeline: list[AdminMetricPoint]
    order_status_breakdown: list[AdminBreakdownItem]
    payment_method_breakdown: list[AdminBreakdownItem]
    review_rating_breakdown: list[AdminBreakdownItem]
    category_distribution: list[AdminBreakdownItem]
    revenue_by_category: list[AdminBreakdownItem]
    orders_by_time: list[AdminHeatmapRow]
    top_desserts: list[AdminTopDessertItem]
    recent_orders: list[AdminRecentOrderItem]
    low_stock_items: list[AdminLowStockItem]


class AdminCategoryBase(ORMModel):
    name: str = Field(min_length=2, max_length=120)
    image: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1500)
    is_active: bool = True

    @field_validator("name", "image", "description", mode="before")
    @classmethod
    def trim_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()


class AdminCategoryCreate(AdminCategoryBase):
    slug: str | None = Field(default=None, max_length=140)


class AdminCategoryUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    image: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1500)
    is_active: bool | None = None

    @field_validator("name", "slug", "image", "description", mode="before")
    @classmethod
    def trim_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()


class AdminCategoryOut(AdminCategoryBase):
    id: UUID
    slug: str
    created_at: datetime
    desserts_count: int = 0


class AdminCategoryOptionOut(ORMModel):
    id: UUID
    name: str
    slug: str
    is_active: bool


class AdminCategoryStats(ORMModel):
    total: int
    active: int
    hidden: int


class AdminCategoryListOut(ORMModel):
    items: list[AdminCategoryOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminCategoryStats


class AdminDessertBase(ORMModel):
    category_id: UUID
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    ingredients: str | None = Field(default=None, max_length=4000)
    price: Decimal = Field(ge=0)
    old_price: Decimal | None = Field(default=None, ge=0)
    stock: int = Field(ge=0)
    status: DessertStatus = DessertStatus.ACTIVE
    is_featured: bool = False
    is_best_seller: bool = False
    is_chef_choice: bool = False
    image_url: str | None = Field(default=None, max_length=500)
    image_urls: list[str] = Field(default_factory=list)

    @field_validator("name", "description", "ingredients", "image_url", mode="before")
    @classmethod
    def trim_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()

    @field_validator("image_urls", mode="before")
    @classmethod
    def normalize_urls(cls, value):
        if not value:
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class AdminDessertCreate(AdminDessertBase):
    slug: str | None = Field(default=None, max_length=220)


class AdminDessertUpdate(ORMModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=180)
    slug: str | None = Field(default=None, max_length=220)
    description: str | None = Field(default=None, max_length=4000)
    ingredients: str | None = Field(default=None, max_length=4000)
    price: Decimal | None = Field(default=None, ge=0)
    old_price: Decimal | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    status: DessertStatus | None = None
    is_featured: bool | None = None
    is_best_seller: bool | None = None
    is_chef_choice: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)
    image_urls: list[str] | None = None

    @field_validator("name", "slug", "description", "ingredients", "image_url", mode="before")
    @classmethod
    def trim_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()

    @field_validator("image_urls", mode="before")
    @classmethod
    def normalize_urls(cls, value):
        if value is None:
            return None
        return [str(item).strip() for item in value if str(item).strip()]


class AdminDessertOut(ORMModel):
    id: UUID
    category_id: UUID
    category_name: str | None = None
    name: str
    slug: str
    description: str | None = None
    ingredients: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    stock: int
    status: DessertStatus
    is_featured: bool
    is_best_seller: bool
    is_chef_choice: bool
    rating_avg: Decimal
    reviews_count: int
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminDessertStats(ORMModel):
    total: int
    active: int
    inactive: int
    out_of_stock: int


class AdminDessertListOut(ORMModel):
    items: list[AdminDessertOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminDessertStats


class AdminGalleryImageBase(ORMModel):
    title: str | None = Field(default=None, max_length=120)
    image_url: str = Field(min_length=1, max_length=500)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True

    @field_validator("title", "image_url", mode="before")
    @classmethod
    def trim_gallery_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()


class AdminGalleryImageCreate(AdminGalleryImageBase):
    pass


class AdminGalleryImageUpdate(ORMModel):
    title: str | None = Field(default=None, max_length=120)
    image_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("title", "image_url", mode="before")
    @classmethod
    def trim_gallery_update_text(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()


class AdminGalleryImageOut(ORMModel):
    id: UUID
    title: str | None = None
    image_url: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminGalleryImageStats(ORMModel):
    total: int
    active: int
    hidden: int


class AdminGalleryImageListOut(ORMModel):
    items: list[AdminGalleryImageOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminGalleryImageStats


class AdminOrderItemOut(ORMModel):
    id: UUID
    dessert_id: UUID | None = None
    dessert_name: str
    quantity: int
    price: Decimal
    total_price: Decimal


class AdminOrderOut(ORMModel):
    id: UUID
    user_id: UUID | None = None
    customer_name: str
    phone: str
    email: str | None = None
    address: str
    delivery_date: date | None = None
    delivery_time: time | None = None
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    status: OrderStatus
    subtotal: Decimal
    delivery_price: Decimal
    total_price: Decimal
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[AdminOrderItemOut] = []


class AdminOrderUpdate(ORMModel):
    status: OrderStatus | None = None
    payment_status: PaymentStatus | None = None
    delivery_price: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value: str | None):
        if value is None:
            return None
        return str(value).strip()


class AdminOrderStats(ORMModel):
    total: int
    pending: int
    processing: int
    delivered: int
    cancelled: int


class AdminOrderListOut(ORMModel):
    items: list[AdminOrderOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminOrderStats


class AdminReviewOut(ORMModel):
    id: UUID
    dessert_id: UUID
    dessert_name: str | None = None
    user_id: UUID
    customer_name: str
    customer_email: str | None = None
    avatar: str | None = None
    rating: int
    text: str | None = None
    is_approved: bool
    created_at: datetime


class AdminReviewUpdate(ORMModel):
    is_approved: bool


class AdminReviewStats(ORMModel):
    total: int
    approved: int
    pending: int
    rejected: int
    average_rating: float


class AdminReviewListOut(ORMModel):
    items: list[AdminReviewOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminReviewStats


class AdminUserOut(ORMModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None = None
    avatar: str | None = None
    role: UserRole
    is_active: bool
    birthday: date | None = None
    bio: str | None = None
    orders_count: int = 0
    reviews_count: int = 0
    created_at: datetime


class AdminCreateUser(ORMModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_app_email(value)


class AdminCustomerStats(ORMModel):
    total: int
    active: int
    inactive: int
    new_this_month: int


class AdminCustomerListOut(ORMModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminCustomerStats
