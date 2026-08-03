"""FastAPI dependency-injection functions for auth and DB access."""
import datetime
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import COOKIE_NAME, decode_access_token
from database import get_session
from models import User

get_db = get_session


async def _load_user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    access_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _load_user_from_token(access_token, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user.last_active_at = datetime.datetime.utcnow()
    await db.commit()
    return user


async def get_current_user_optional(
    access_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    user = await _load_user_from_token(access_token, db)
    if user is not None:
        user.last_active_at = datetime.datetime.utcnow()
        await db.commit()
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
