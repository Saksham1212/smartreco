"""Admin panel: dashboard, product CRUD, events explorer, recommendations explorer."""
import datetime
import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from dependencies import get_current_user_optional, get_db
from models import Event, Product, Recommendation, User
from routers.products import (
    create_product_service,
    hard_delete_product_service,
    soft_delete_product_service,
    update_product_service,
)
from schemas import ProductCreate, ProductUpdate
from templating import templates

logger = logging.getLogger("smartreco.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


def _flash_redirect(path: str, key: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{path}?{key}={quote(message)}", status_code=303)


async def _gate(user: Optional[User], request: Request):
    """Returns a RedirectResponse/TemplateResponse to short-circuit with, or None to proceed."""
    if user is None:
        return RedirectResponse(
            url=f"/login?error=Please+log+in.&next={quote(str(request.url))}", status_code=303
        )
    if not user.is_admin:
        return templates.TemplateResponse(
            "403.html", {"request": request, "user": user}, status_code=403
        )
    return None


@router.get("")
async def admin_dashboard(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_products = (await db.execute(select(func.count(Product.id)).where(Product.is_active.is_(True)))).scalar_one()
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    events_24h = (await db.execute(select(func.count(Event.id)).where(Event.created_at >= since))).scalar_one()
    total_recommendations = (await db.execute(select(func.count(Recommendation.id)))).scalar_one()

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "total_users": total_users,
            "total_products": total_products,
            "events_24h": events_24h,
            "total_recommendations": total_recommendations,
        },
    )


@router.get("/products")
async def admin_products(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    result = await db.execute(select(Product).order_by(Product.created_at.desc()))
    products = result.scalars().all()
    return templates.TemplateResponse(
        "admin/products.html", {"request": request, "user": user, "products": products}
    )


@router.get("/products/new")
async def admin_product_new_form(
    request: Request, user: Optional[User] = Depends(get_current_user_optional)
):
    gate = await _gate(user, request)
    if gate:
        return gate
    return templates.TemplateResponse(
        "admin/product_form.html", {"request": request, "user": user, "product": None}
    )


@router.post("/products/new")
async def admin_product_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    difficulty_level: str = Form(...),
    tags: str = Form(""),
    instructor_name: str = Form(""),
    duration_hours: float = Form(0),
    thumbnail_url: str = Form(""),
    is_active: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    try:
        payload = ProductCreate(
            title=title,
            description=description,
            category=category,
            price=price,
            difficulty_level=difficulty_level,
            tags=tags,
            instructor_name=instructor_name,
            duration_hours=duration_hours,
            thumbnail_url=thumbnail_url or None,
            is_active=is_active is not None,
        )
    except ValidationError as exc:
        return _flash_redirect("/admin/products/new", "error", exc.errors()[0]["msg"])

    try:
        await create_product_service(db, payload)
    except Exception:
        logger.exception("Failed to create product")
        return _flash_redirect("/admin/products/new", "error", "Failed to create product.")

    return _flash_redirect("/admin/products", "success", f"Product '{payload.title}' created.")


@router.get("/products/{product_id}/edit")
async def admin_product_edit_form(
    product_id: int,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    product = await db.get(Product, product_id)
    if product is None:
        return _flash_redirect("/admin/products", "error", "Product not found.")

    return templates.TemplateResponse(
        "admin/product_form.html", {"request": request, "user": user, "product": product}
    )


@router.post("/products/{product_id}/edit")
async def admin_product_update(
    product_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    difficulty_level: str = Form(...),
    tags: str = Form(""),
    instructor_name: str = Form(""),
    duration_hours: float = Form(0),
    thumbnail_url: str = Form(""),
    is_active: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    product = await db.get(Product, product_id)
    if product is None:
        return _flash_redirect("/admin/products", "error", "Product not found.")

    try:
        payload = ProductUpdate(
            title=title,
            description=description,
            category=category,
            price=price,
            difficulty_level=difficulty_level,
            tags=tags,
            instructor_name=instructor_name,
            duration_hours=duration_hours,
            thumbnail_url=thumbnail_url or None,
            is_active=is_active is not None,
        )
    except ValidationError as exc:
        return _flash_redirect(f"/admin/products/{product_id}/edit", "error", exc.errors()[0]["msg"])

    try:
        await update_product_service(db, product, payload)
    except Exception:
        logger.exception("Failed to update product %s", product_id)
        return _flash_redirect(f"/admin/products/{product_id}/edit", "error", "Failed to update product.")

    return _flash_redirect("/admin/products", "success", f"Product '{payload.title}' updated.")


@router.post("/products/{product_id}/delete")
async def admin_product_soft_delete(
    product_id: int,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    product = await db.get(Product, product_id)
    if product is None:
        return _flash_redirect("/admin/products", "error", "Product not found.")

    try:
        await soft_delete_product_service(db, product)
    except Exception:
        logger.exception("Failed to soft-delete product %s", product_id)
        return _flash_redirect("/admin/products", "error", "Failed to delete product.")

    return _flash_redirect("/admin/products", "success", f"Product '{product.title}' deactivated.")


@router.post("/products/{product_id}/hard-delete")
async def admin_product_hard_delete(
    product_id: int,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    product = await db.get(Product, product_id)
    if product is None:
        return _flash_redirect("/admin/products", "error", "Product not found.")

    title = product.title
    try:
        await hard_delete_product_service(db, product)
    except Exception:
        logger.exception("Failed to hard-delete product %s", product_id)
        return _flash_redirect("/admin/products", "error", "Failed to permanently delete product.")

    return _flash_redirect("/admin/products", "success", f"Product '{title}' permanently deleted.")


@router.get("/events")
async def admin_events(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    result = await db.execute(
        select(Event)
        .options(selectinload(Event.user), selectinload(Event.product))
        .order_by(Event.created_at.desc())
        .limit(200)
    )
    events = result.scalars().all()
    return templates.TemplateResponse("admin/events.html", {"request": request, "user": user, "events": events})


@router.get("/recommendations")
async def admin_recommendations(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    gate = await _gate(user, request)
    if gate:
        return gate

    result = await db.execute(
        select(Recommendation, User)
        .join(User, User.id == Recommendation.user_id)
        .order_by(Recommendation.updated_at.desc())
        .limit(200)
    )
    rows = result.all()
    return templates.TemplateResponse(
        "admin/recommendations.html", {"request": request, "user": user, "rows": rows}
    )
