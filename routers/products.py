"""Product JSON API + dual-write service functions shared with the admin router."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import vector_store
from dependencies import get_db
from models import Event, Product, Recommendation
from schemas import ProductCreate, ProductOut, ProductUpdate

logger = logging.getLogger("smartreco.products")

router = APIRouter(prefix="/api/products", tags=["products"])


def _parse_optional_float(value: Optional[str]) -> Optional[float]:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Dual-write service functions (used by admin router and seed)
# ---------------------------------------------------------------------------

async def create_product_service(db: AsyncSession, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await vector_store.upsert_product(product)
    return product


async def update_product_service(db: AsyncSession, product: Product, data: ProductUpdate) -> Product:
    for field, value in data.model_dump().items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    if product.is_active:
        await vector_store.upsert_product(product)
    else:
        await vector_store.delete_product(product.id)
    return product


async def soft_delete_product_service(db: AsyncSession, product: Product) -> None:
    product.is_active = False
    await db.commit()
    await vector_store.delete_product(product.id)


async def hard_delete_product_service(db: AsyncSession, product: Product) -> None:
    import json

    await db.execute(Event.__table__.delete().where(Event.product_id == product.id))

    recs_result = await db.execute(select(Recommendation))
    for rec in recs_result.scalars().all():
        try:
            ids = json.loads(rec.product_ids_json or "[]")
        except json.JSONDecodeError:
            ids = []
        if product.id in ids:
            await db.delete(rec)

    await vector_store.delete_product(product.id)
    await db.delete(product)
    await db.commit()


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@router.get("")
async def list_products(
    category: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    try:
        min_price_val = _parse_optional_float(min_price)
        max_price_val = _parse_optional_float(max_price)
        stmt = select(Product).where(Product.is_active.is_(True))
        count_stmt = select(func.count(Product.id)).where(Product.is_active.is_(True))

        if category:
            stmt = stmt.where(Product.category == category)
            count_stmt = count_stmt.where(Product.category == category)
        if difficulty_level:
            stmt = stmt.where(Product.difficulty_level == difficulty_level)
            count_stmt = count_stmt.where(Product.difficulty_level == difficulty_level)
        if min_price_val is not None:
            stmt = stmt.where(Product.price >= min_price_val)
            count_stmt = count_stmt.where(Product.price >= min_price_val)
        if max_price_val is not None:
            stmt = stmt.where(Product.price <= max_price_val)
            count_stmt = count_stmt.where(Product.price <= max_price_val)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Product.title.like(like), Product.description.like(like)))
            count_stmt = count_stmt.where(or_(Product.title.like(like), Product.description.like(like)))

        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        products = (await db.execute(stmt)).scalars().all()

        return {
            "products": [ProductOut.model_validate(p).model_dump(mode="json") for p in products],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception:
        logger.exception("Failed to list products")
        raise HTTPException(status_code=500, detail={"error": "Failed to list products"})


@router.get("/{product_id}")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail={"error": "Product not found"})
    return ProductOut.model_validate(product).model_dump(mode="json")
