"""Authentication routes: register, login, logout (form-based, cookie JWT)."""
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import COOKIE_NAME, create_access_token, hash_password, verify_password
from config import settings
from dependencies import get_db
from models import User
from schemas import UserCreate

logger = logging.getLogger("smartreco.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _redirect_with_message(path: str, key: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{path}?{key}={quote(message)}", status_code=303)


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = UserCreate(email=email, password=password, full_name=full_name)
    except ValidationError as exc:
        first_error = exc.errors()[0]["msg"]
        return _redirect_with_message("/register", "error", first_error)

    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        return _redirect_with_message("/register", "error", "An account with that email already exists.")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        logger.exception("Failed to create user %s", payload.email)
        return _redirect_with_message("/register", "error", "Something went wrong. Please try again.")

    token = create_access_token(user.id, user.email, user.is_admin)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return response


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return _redirect_with_message("/login", "error", "Invalid email or password.")
    if not user.is_active:
        return _redirect_with_message("/login", "error", "This account has been deactivated.")

    token = create_access_token(user.id, user.email, user.is_admin)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
