"""Behavioral event ingestion. Must be fast and never block the frontend."""
import datetime
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent import maybe_run_agent
from dependencies import get_current_user_optional, get_db
from models import Event, User
from schemas import EventIn

logger = logging.getLogger("smartreco.events")

router = APIRouter(prefix="/api/events", tags=["events"])


def _parse_timestamp(ts: Optional[str]) -> datetime.datetime:
    if ts:
        try:
            parsed = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.datetime.utcnow()


@router.post("/batch")
async def batch_events(
    events: list[EventIn],
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    if user is None:
        # Silently discard — tracking only applies to authenticated users.
        return JSONResponse(status_code=200, content={"status": "discarded", "reason": "unauthenticated"})

    if not events:
        return JSONResponse(status_code=200, content={"status": "ok", "inserted": 0})

    try:
        rows = [
            Event(
                user_id=user.id,
                event_type=e.event_type,
                product_id=e.product_id,
                search_query=e.search_query,
                metadata_json=json.dumps(e.metadata) if e.metadata else None,
                created_at=_parse_timestamp(e.timestamp),
            )
            for e in events
        ]
        db.add_all(rows)
        user.last_active_at = datetime.datetime.utcnow()
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to insert event batch for user %s", user.id)
        return JSONResponse(
            status_code=500, content={"error": "Failed to record events", "detail": "internal error"}
        )

    background_tasks.add_task(maybe_run_agent, user.id)

    return JSONResponse(status_code=200, content={"status": "ok", "inserted": len(rows)})
