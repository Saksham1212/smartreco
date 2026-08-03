"""Recommendation retrieval API — polled by the dashboard widget."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models import Product, Recommendation, User

logger = logging.getLogger("smartreco.recommendations")

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/me")
async def get_my_recommendation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rec = (
            await db.execute(select(Recommendation).where(Recommendation.user_id == user.id))
        ).scalar_one_or_none()

        if rec is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "No recommendation yet",
                    "detail": "We're still learning your preferences. Keep browsing and check back soon.",
                },
            )

        try:
            product_ids = json.loads(rec.product_ids_json or "[]")
        except json.JSONDecodeError:
            product_ids = []

        products_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
        products_by_id = {p.id: p for p in products_result.scalars().all()}

        product_cards = []
        for pid in product_ids:
            p = products_by_id.get(pid)
            if p is None:
                continue
            product_cards.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "category": p.category,
                    "difficulty_level": p.difficulty_level,
                    "price": p.price,
                    "thumbnail_url": p.thumbnail_url,
                    "description": (p.description[:200] + "...") if len(p.description) > 200 else p.description,
                }
            )

        return {
            "narrative": rec.narrative,
            "products": product_cards,
            "behavioral_summary": rec.behavioral_summary,
            "updated_at": rec.updated_at.isoformat(),
            "events_count_at_generation": rec.events_count_at_generation,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch recommendation for user %s", user.id)
        raise HTTPException(status_code=500, detail={"error": "Failed to fetch recommendation"})
