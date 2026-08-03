"""Server-rendered Jinja2 pages."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import vector_store
from dependencies import get_current_user_optional, get_db
from models import Product, User
from templating import templates

logger = logging.getLogger("smartreco.pages")

router = APIRouter(tags=["pages"])

PAGE_SIZE = 12


def _parse_optional_float(value: Optional[str]) -> Optional[float]:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


@router.get("/")
async def homepage(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    featured_result = await db.execute(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc()).limit(8)
    )
    featured = featured_result.scalars().all()

    categories_result = await db.execute(
        select(distinct(Product.category)).where(Product.is_active.is_(True))
    )
    categories = sorted([c[0] for c in categories_result.all()])

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user, "featured_products": featured, "categories": categories},
    )


@router.get("/products")
async def product_listing(
    request: Request,
    category: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    category = category or None
    difficulty_level = difficulty_level or None
    min_price = _parse_optional_float(min_price)
    max_price = _parse_optional_float(max_price)

    stmt = select(Product).where(Product.is_active.is_(True))
    count_stmt = select(func.count(Product.id)).where(Product.is_active.is_(True))

    if category:
        stmt = stmt.where(Product.category == category)
        count_stmt = count_stmt.where(Product.category == category)
    if difficulty_level:
        stmt = stmt.where(Product.difficulty_level == difficulty_level)
        count_stmt = count_stmt.where(Product.difficulty_level == difficulty_level)
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
        count_stmt = count_stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
        count_stmt = count_stmt.where(Product.price <= max_price)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Product.created_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    products = (await db.execute(stmt)).scalars().all()

    all_categories_result = await db.execute(
        select(distinct(Product.category)).where(Product.is_active.is_(True))
    )
    categories = sorted([c[0] for c in all_categories_result.all()])

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse(
        "products/list.html",
        {
            "request": request,
            "user": user,
            "products": products,
            "categories": categories,
            "selected_category": category,
            "selected_difficulty": difficulty_level,
            "min_price": min_price,
            "max_price": max_price,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/products/{product_id}")
async def product_detail(
    product_id: int,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or not product.is_active:
        return templates.TemplateResponse(
            "404.html", {"request": request, "user": user}, status_code=404
        )

    related_result = await db.execute(
        select(Product)
        .where(Product.category == product.category, Product.id != product.id, Product.is_active.is_(True))
        .limit(4)
    )
    related = related_result.scalars().all()

    return templates.TemplateResponse(
        "products/detail.html",
        {"request": request, "user": user, "product": product, "related_products": related},
    )


@router.get("/search")
async def search_page(
    request: Request,
    q: Optional[str] = None,
    mode: str = "keyword",
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    results = []
    if q:
        if mode == "semantic":
            try:
                semantic_results = await vector_store.semantic_search(q, n_results=20, where={"is_active": True})
                ids = [int(r["metadata"]["product_id"]) for r in semantic_results if r["metadata"].get("product_id")]
                if ids:
                    products_result = await db.execute(select(Product).where(Product.id.in_(ids)))
                    products_by_id = {p.id: p for p in products_result.scalars().all()}
                    results = [products_by_id[i] for i in ids if i in products_by_id]
            except Exception:
                logger.exception("Semantic search failed for query=%r", q)
                results = []
        else:
            like = f"%{q}%"
            result = await db.execute(
                select(Product).where(
                    Product.is_active.is_(True),
                    or_(Product.title.like(like), Product.description.like(like)),
                )
            )
            results = result.scalars().all()

    return templates.TemplateResponse(
        "products/search.html",
        {"request": request, "user": user, "query": q or "", "mode": mode, "results": results},
    )


@router.get("/login")
async def login_page(
    request: Request, user: Optional[User] = Depends(get_current_user_optional)
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request, "user": None})


@router.get("/register")
async def register_page(
    request: Request, user: Optional[User] = Depends(get_current_user_optional)
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("auth/register.html", {"request": request, "user": None})


@router.get("/dashboard")
async def dashboard_page(
    request: Request, user: Optional[User] = Depends(get_current_user_optional)
):
    if user is None:
        return RedirectResponse(url="/login?error=Please+log+in+to+view+your+dashboard.", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
