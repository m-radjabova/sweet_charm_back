from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.category import Category
from app.models.dessert import Dessert
from app.models.dessert_image import DessertImage
from app.models.enums import DessertStatus
from app.models.gallery_image import GalleryImage
from app.models.review import Review
from app.models.user import User
from app.schemas.user import AdminCreate
from app.services.user_service import UserService

load_dotenv(override=True)


CATEGORY_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "name": "Cakes",
        "slug": "cakes",
        "description": "Layered celebration cakes with soft sponge, fresh cream and playful Sweet Charm styling.",
        "base_price": "88.00",
        "step": "9.00",
        "stock_base": 6,
        "image_pool": [
            "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1533134242443-d4fd215305ad?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1550617931-e17a7b70dce2?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1464306076886-da185f6a9d05?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Shortcake",
            "Chocolate Dream Cake",
            "Red Velvet Cake",
            "Blueberry Cheesecake",
            "Matcha Layer Cake",
        ],
    },
    {
        "name": "Cupcakes",
        "slug": "cupcakes",
        "description": "Cute single-serve cupcakes finished with silky cream swirls and colorful toppings.",
        "base_price": "18.00",
        "step": "2.50",
        "stock_base": 18,
        "image_pool": [
            "https://images.unsplash.com/photo-1486427944299-d1955d23e34d?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1587668178277-295251f900ce?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Cupcake",
            "Vanilla Cream Cupcake",
            "Chocolate Fudge Cupcake",
            "Red Velvet Cupcake",
            "Oreo Cupcake",
        ],
    },
    {
        "name": "Cookies",
        "slug": "cookies",
        "description": "Freshly baked cookies with crisp edges, soft centers and rich buttery flavor.",
        "base_price": "10.00",
        "step": "1.75",
        "stock_base": 26,
        "image_pool": [
            "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1495214783159-3503fd1b572d?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Chocolate Chip Cookie",
            "Double Chocolate Cookie",
            "Butter Cookie",
            "Red Velvet Cookie",
            "Matcha Cookie",
        ],
    },
    {
        "name": "Mochi",
        "slug": "mochi",
        "description": "Soft and chewy mochi with creamy centers and a smooth pastel finish.",
        "base_price": "17.00",
        "step": "2.00",
        "stock_base": 20,
        "image_pool": [
            "https://images.unsplash.com/photo-1563805042-7684c019e1cb?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1614707267537-b85aaf00c4b7?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1627308595229-7830a5c91f9f?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1541599540903-216a46ca1dc0?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Mochi",
            "Mango Mochi",
            "Matcha Mochi",
            "Chocolate Mochi",
            "Vanilla Mochi",
        ],
    },
    {
        "name": "Macarons",
        "slug": "macarons",
        "description": "Elegant French-style macarons with delicate shells and creamy fillings.",
        "base_price": "15.00",
        "step": "1.50",
        "stock_base": 24,
        "image_pool": [
            "https://images.unsplash.com/photo-1558326567-98ae2405596b?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1569864358642-9d1684040f43?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1511911063855-2bf39afa5b2e?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Macaron",
            "Vanilla Macaron",
            "Chocolate Macaron",
            "Pistachio Macaron",
            "Raspberry Macaron",
        ],
    },
    {
        "name": "Puddings",
        "slug": "puddings",
        "description": "Silky puddings with glossy toppings and a light, spoonable texture.",
        "base_price": "14.00",
        "step": "1.80",
        "stock_base": 18,
        "image_pool": [
            "https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1470124182917-cc6e71b22ecc?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1505253216365-28c066ee10ca?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1562440499-64c9a111f713?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Caramel Pudding",
            "Vanilla Pudding",
            "Chocolate Pudding",
            "Strawberry Pudding",
            "Mango Pudding",
        ],
    },
    {
        "name": "Donuts",
        "slug": "donuts",
        "description": "Fluffy donuts glazed with glossy toppings, crunchy crumbs and sweet drizzles.",
        "base_price": "16.00",
        "step": "2.00",
        "stock_base": 20,
        "image_pool": [
            "https://images.unsplash.com/photo-1551024601-bec78aea704b?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1504754524776-8f4f37790ca0?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1527515545081-5db817172677?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Donut",
            "Chocolate Donut",
            "Vanilla Glazed Donut",
            "Oreo Donut",
            "Caramel Donut",
        ],
    },
    {
        "name": "Drinks",
        "slug": "drinks",
        "description": "Comfort drinks and cafe favorites blended to pair perfectly with our desserts.",
        "base_price": "19.00",
        "step": "2.50",
        "stock_base": 30,
        "image_pool": [
            "https://images.unsplash.com/photo-1464306076886-da185f6a9d05?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1517701604599-bb29b565090c?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1515823064-d6e0c04616a7?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Strawberry Milkshake",
            "Matcha Latte",
            "Caramel Latte",
            "Berry Smoothie",
            "Hot Chocolate",
        ],
    },
    {
        "name": "Gift Boxes",
        "slug": "gift-boxes",
        "description": "Curated dessert boxes for birthdays, sharing tables and cheerful surprise gifting.",
        "base_price": "68.00",
        "step": "12.00",
        "stock_base": 8,
        "image_pool": [
            "https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1511920170033-f8396924c348?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1521017432531-fbd92d768814?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Sweet Gift Box",
            "Birthday Dessert Box",
            "Premium Macaron Box",
            "Cupcake Party Box",
            "Family Treat Box",
        ],
    },
    {
        "name": "Specials",
        "slug": "specials",
        "description": "Signature Sweet Charm favorites with extra styling, seasonal flavor and gift-worthy presentation.",
        "base_price": "58.00",
        "step": "11.00",
        "stock_base": 10,
        "image_pool": [
            "https://images.unsplash.com/photo-1571115764595-644a1f56a55c?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1550617931-e17a7b70dce2?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1533134242443-d4fd215305ad?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=1200&q=80",
        ],
        "items": [
            "Bunnynuts Special",
            "SweetCharm Signature Cake",
            "Sakura Strawberry Roll",
            "Pink Cloud Cheesecake",
            "Kawaii Dessert Set",
        ],
    },
]

REVIEWS: list[dict[str, Any]] = [
    {
        "user": {
            "full_name": "Daniel Clark",
            "email": "daniel.clark@sweetcharm.local",
            "phone": "+998901110101",
        },
        "dessert_slug": "sweetcharm-signature-cake",
        "rating": 5,
        "text": "Beautiful design, soft texture and a premium finish. This felt like the perfect Sweet Charm signature dessert.",
        "created_at": datetime(2024, 2, 12, 10, 30, tzinfo=timezone.utc),
    },
    {
        "user": {
            "full_name": "Sarah Smith",
            "email": "sarah.smith@sweetcharm.local",
            "phone": "+998901110102",
        },
        "dessert_slug": "matcha-layer-cake",
        "rating": 5,
        "text": "The matcha flavor was balanced and elegant. I would absolutely order this cake again for a special day.",
        "created_at": datetime(2024, 2, 23, 14, 15, tzinfo=timezone.utc),
    },
    {
        "user": {
            "full_name": "Jessica Taylor",
            "email": "jessica.taylor@sweetcharm.local",
            "phone": "+998901110103",
        },
        "dessert_slug": "pink-cloud-cheesecake",
        "rating": 5,
        "text": "Super cute, creamy and camera-ready. The cheesecake slice looked dreamy and tasted even better.",
        "created_at": datetime(2024, 3, 9, 9, 45, tzinfo=timezone.utc),
    },
    {
        "user": {
            "full_name": "Emily Brown",
            "email": "emily.brown@sweetcharm.local",
            "phone": "+998901110104",
        },
        "dessert_slug": "mango-mochi",
        "rating": 4,
        "text": "Soft mochi, fresh mango taste and lovely packaging. It is light, fun and easy to recommend.",
        "created_at": datetime(2024, 3, 17, 11, 20, tzinfo=timezone.utc),
    },
    {
        "user": {
            "full_name": "Michael Lee",
            "email": "michael.lee@sweetcharm.local",
            "phone": "+998901110105",
        },
        "dessert_slug": "caramel-pudding",
        "rating": 5,
        "text": "Silky texture and clean caramel flavor. One of the most comforting desserts on the menu.",
        "created_at": datetime(2024, 3, 28, 16, 5, tzinfo=timezone.utc),
    },
]

GALLERY_IMAGES: list[dict[str, Any]] = [
    {
        "title": "Strawberry cake and tea",
        "image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 1,
    },
    {
        "title": "SweetCharm cafe counter",
        "image_url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 2,
    },
    {
        "title": "Opening the cafe",
        "image_url": "https://images.unsplash.com/photo-1521017432531-fbd92d768814?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 3,
    },
    {
        "title": "Preparing floral decor",
        "image_url": "https://images.unsplash.com/photo-1511920170033-f8396924c348?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 4,
    },
    {
        "title": "Packing sweet orders",
        "image_url": "https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 5,
    },
    {
        "title": "Tea and pastry moment",
        "image_url": "https://images.unsplash.com/photo-1504754524776-8f4f37790ca0?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 6,
    },
    {
        "title": "Serving fresh tea",
        "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1200&q=80",
        "sort_order": 7,
    },
]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", value)


def rotate_images(image_pool: list[str], offset: int, count: int = 3) -> list[str]:
    size = len(image_pool)
    return [image_pool[(offset + index) % size] for index in range(count)]


def infer_keywords(name: str) -> list[str]:
    keywords = [
        keyword
        for keyword in (
            "strawberry",
            "chocolate",
            "red velvet",
            "blueberry",
            "matcha",
            "mango",
            "vanilla",
            "oreo",
            "pistachio",
            "raspberry",
            "caramel",
            "berry",
            "sakura",
            "pink cloud",
            "bunnynuts",
            "signature",
            "premium",
            "family",
            "birthday",
            "kawaii",
        )
        if keyword in name.lower()
    ]
    return keywords or ["sweet cream"]


def build_description(name: str, category_name: str) -> str:
    flavor_text = ", ".join(infer_keywords(name))
    return (
        f"{name} from our {category_name} collection with {flavor_text} notes, neat presentation "
        "and a soft Sweet Charm finish."
    )


def build_ingredients(name: str, category_slug: str) -> str:
    ingredients = infer_keywords(name)

    category_bases = {
        "cakes": ["sponge", "whipped cream"],
        "cupcakes": ["vanilla sponge", "buttercream"],
        "cookies": ["flour", "butter"],
        "mochi": ["glutinous rice flour", "fresh cream"],
        "macarons": ["almond flour", "ganache"],
        "puddings": ["milk", "cream"],
        "donuts": ["yeast dough", "glaze"],
        "drinks": ["milk", "sweet syrup"],
        "gift-boxes": ["assorted desserts", "decorative box"],
        "specials": ["signature cream", "seasonal garnish"],
    }
    base = category_bases.get(category_slug, ["cream", "sugar"])
    return ", ".join([ingredient.title() for ingredient in ingredients] + base + ["Sugar"])


def build_rating(index: int, category_slug: str) -> Decimal:
    bonus = Decimal("0.10") if category_slug in {"specials", "cakes"} else Decimal("0.00")
    rating = Decimal("4.58") + Decimal(index % 5) * Decimal("0.07") + bonus
    return min(rating, Decimal("4.98")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_catalog() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    categories: list[dict[str, Any]] = []
    desserts: list[dict[str, Any]] = []

    for blueprint in CATEGORY_BLUEPRINTS:
        categories.append(
            {
                "name": blueprint["name"],
                "slug": blueprint["slug"],
                "image": blueprint["image_pool"][0],
                "description": blueprint["description"],
            }
        )

        base_price = Decimal(blueprint["base_price"])
        step = Decimal(blueprint["step"])

        for index, dessert_name in enumerate(blueprint["items"]):
            price = (base_price + step * index).quantize(Decimal("0.01"))
            old_price = (price + step + Decimal("4.00")).quantize(Decimal("0.01")) if index % 2 == 0 else None
            image_urls = rotate_images(blueprint["image_pool"], index, count=3)

            desserts.append(
                {
                    "name": dessert_name,
                    "slug": slugify(dessert_name),
                    "category_slug": blueprint["slug"],
                    "description": build_description(dessert_name, blueprint["name"]),
                    "ingredients": build_ingredients(dessert_name, blueprint["slug"]),
                    "price": price,
                    "old_price": old_price,
                    "stock": blueprint["stock_base"] + (index % 4) * 3,
                    "rating_avg": build_rating(index, blueprint["slug"]),
                    "reviews_count": 10 + index * 3,
                    "is_featured": blueprint["slug"] in {"cakes", "specials", "gift-boxes"} or index == 0,
                    "is_best_seller": index < 2 or blueprint["slug"] in {"mochi", "drinks"},
                    "image_url": image_urls[0],
                    "image_urls": image_urls,
                }
            )

    return categories, desserts


CATEGORIES, DESSERTS = build_catalog()


def upsert_admin(user_service: UserService) -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    admin_full_name = os.getenv("ADMIN_FULL_NAME", "Sweet Charm Admin").strip()

    if not admin_email or not admin_password:
        print("Admin credentials topilmadi, admin seed skip qilindi")
        return

    existing_admin = user_service.get_by_email(admin_email)
    if existing_admin:
        print("Admin allaqachon mavjud")
        return

    user_service.create_admin(
        AdminCreate(
            full_name=admin_full_name,
            email=admin_email,
            password=admin_password,
        )
    )
    print("Admin yaratildi")


def upsert_category(db, payload: dict[str, Any]) -> Category:
    category = db.execute(select(Category).where(Category.slug == payload["slug"])).scalar_one_or_none()
    if category is None:
        category = Category(slug=payload["slug"])

    category.name = payload["name"]
    category.image = payload["image"]
    category.description = payload["description"]
    category.is_active = True
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def sync_dessert_images(dessert: Dessert, image_urls: list[str]) -> None:
    ordered_images = sorted(dessert.images, key=lambda image: (not image.is_main, image.created_at))

    while len(ordered_images) < len(image_urls):
        new_image = DessertImage(is_main=False)
        dessert.images.append(new_image)
        ordered_images.append(new_image)

    for index, image_url in enumerate(image_urls):
        ordered_images[index].image_url = image_url
        ordered_images[index].is_main = index == 0

    for extra_image in ordered_images[len(image_urls):]:
        dessert.images.remove(extra_image)


def upsert_desserts(db, categories_by_slug: dict[str, Category]) -> tuple[int, int]:
    existing_desserts = {
        dessert.slug: dessert
        for dessert in db.execute(select(Dessert).options(selectinload(Dessert.images))).scalars()
    }

    created = 0
    updated = 0

    for payload in DESSERTS:
        category = categories_by_slug[payload["category_slug"]]
        dessert = existing_desserts.get(payload["slug"])
        is_new = dessert is None

        if dessert is None:
            dessert = Dessert(slug=payload["slug"])

        dessert.name = payload["name"]
        dessert.category_id = category.id
        dessert.description = payload["description"]
        dessert.ingredients = payload["ingredients"]
        dessert.price = payload["price"]
        dessert.old_price = payload["old_price"]
        dessert.stock = payload["stock"]
        dessert.status = DessertStatus.ACTIVE
        dessert.is_featured = payload["is_featured"]
        dessert.is_best_seller = payload["is_best_seller"]
        dessert.rating_avg = payload["rating_avg"]
        dessert.reviews_count = payload["reviews_count"]

        sync_dessert_images(dessert, payload["image_urls"])

        db.add(dessert)
        db.commit()
        db.refresh(dessert)

        if is_new:
            created += 1
        else:
            updated += 1

    return created, updated


def upsert_review_user(db, payload: dict[str, str]) -> User:
    email = payload["email"].strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            full_name=payload["full_name"].strip(),
            email=email,
            phone=payload["phone"].strip(),
            password_hash=hash_password("SweetCharm123!"),
        )
    else:
        user.full_name = payload["full_name"].strip()
        user.phone = payload["phone"].strip()

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def upsert_reviews(db) -> tuple[int, int]:
    desserts = {dessert.slug: dessert for dessert in db.execute(select(Dessert)).scalars().all()}
    created = 0
    updated = 0

    for payload in REVIEWS:
        user = upsert_review_user(db, payload["user"])
        dessert = desserts.get(payload["dessert_slug"])
        if dessert is None:
            continue

        review = db.execute(
            select(Review).where(
                Review.user_id == user.id,
                Review.dessert_id == dessert.id,
                Review.order_id.is_(None),
            )
        ).scalar_one_or_none()
        is_new = review is None

        if review is None:
            review = Review(
                user_id=user.id,
                dessert_id=dessert.id,
                order_id=None,
            )

        review.rating = payload["rating"]
        review.text = payload["text"]
        review.is_approved = True
        review.created_at = payload["created_at"]
        db.add(review)
        db.commit()
        db.refresh(review)

        if is_new:
            created += 1
        else:
            updated += 1

    for dessert in desserts.values():
        approved_reviews = db.execute(
            select(Review).where(
                Review.dessert_id == dessert.id,
                Review.is_approved.is_(True),
            )
        ).scalars().all()

        if approved_reviews:
            dessert.reviews_count = len(approved_reviews)
            dessert.rating_avg = Decimal(
                str(round(sum(review.rating for review in approved_reviews) / len(approved_reviews), 2))
            )
            db.add(dessert)

    db.commit()
    return created, updated


def upsert_gallery_images(db) -> tuple[int, int]:
    existing_images = {image.sort_order: image for image in db.execute(select(GalleryImage)).scalars().all()}
    created = 0
    updated = 0

    for payload in GALLERY_IMAGES:
        gallery_image = existing_images.get(payload["sort_order"])
        is_new = gallery_image is None

        if gallery_image is None:
            gallery_image = GalleryImage(sort_order=payload["sort_order"])

        gallery_image.title = payload["title"]
        gallery_image.image_url = payload["image_url"]
        gallery_image.sort_order = payload["sort_order"]
        gallery_image.is_active = True

        db.add(gallery_image)
        db.commit()
        db.refresh(gallery_image)

        if is_new:
            created += 1
        else:
            updated += 1

    return created, updated


def main() -> None:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        upsert_admin(user_service)

        categories_by_slug = {payload["slug"]: upsert_category(db, payload) for payload in CATEGORIES}
        print(f"Category seedlandi: {len(categories_by_slug)} ta category tayyor")

        created, updated = upsert_desserts(db, categories_by_slug)
        print(f"Desserts seedlandi: {created} ta yaratildi, {updated} ta yangilandi")

        reviews_created, reviews_updated = upsert_reviews(db)
        print(f"Reviews seedlandi: {reviews_created} ta yaratildi, {reviews_updated} ta yangilandi")

        gallery_created, gallery_updated = upsert_gallery_images(db)
        print(f"Gallery seedlandi: {gallery_created} ta yaratildi, {gallery_updated} ta yangilandi")
    finally:
        db.close()


if __name__ == "__main__":
    main()
