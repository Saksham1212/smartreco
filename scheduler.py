"""APScheduler setup: daily email digest job + periodic vector-store retry job."""
import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from config import settings
from email_service import render_digest_html, send_email
from models import EmailDeliveryLog, Recommendation, User

logger = logging.getLogger("smartreco.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def run_daily_digest_job():
    from database import AsyncSessionLocal

    logger.info("Starting daily digest job")
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Recommendation, User)
            .join(User, User.id == Recommendation.user_id)
            .where(
                Recommendation.updated_at >= cutoff,
                User.is_active.is_(True),
            )
        )
        rows = result.all()

        sent, skipped, failed = 0, 0, 0

        for recommendation, user in rows:
            import json

            from models import Product

            try:
                product_ids = json.loads(recommendation.product_ids_json or "[]")
            except json.JSONDecodeError:
                product_ids = []

            products_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
            products_by_id = {p.id: p for p in products_result.scalars().all()}
            products = [
                {
                    "id": pid,
                    "title": products_by_id[pid].title,
                    "category": products_by_id[pid].category,
                    "difficulty_level": products_by_id[pid].difficulty_level,
                    "price": products_by_id[pid].price,
                }
                for pid in product_ids
                if pid in products_by_id
            ]

            if not user.email or not settings.EMAIL_ENABLED:
                log = EmailDeliveryLog(
                    user_id=user.id,
                    recommendation_id=recommendation.id,
                    status="skipped",
                    error_message=None if settings.EMAIL_ENABLED else "EMAIL_ENABLED is false",
                )
                db.add(log)
                skipped += 1
            else:
                html = render_digest_html(user.full_name, recommendation.narrative, products)
                success, error = await send_email(
                    user.email, "Your personalized course recommendations", html
                )
                log = EmailDeliveryLog(
                    user_id=user.id,
                    recommendation_id=recommendation.id,
                    status="sent" if success else "failed",
                    error_message=error,
                )
                db.add(log)
                sent += 1 if success else 0
                failed += 0 if success else 1

            await db.commit()
            await asyncio.sleep(0.5)

        logger.info("Daily digest job complete: sent=%d skipped=%d failed=%d", sent, skipped, failed)


async def run_vector_retry_job():
    from database import AsyncSessionLocal
    from models import Product
    from vector_store import retry_failed_writes

    await retry_failed_writes(AsyncSessionLocal, Product)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(
        run_daily_digest_job,
        trigger=CronTrigger(hour=settings.DAILY_DIGEST_HOUR, minute=settings.DAILY_DIGEST_MINUTE),
        id="daily_digest",
        replace_existing=True,
    )

    _scheduler.add_job(
        run_vector_retry_job,
        trigger=IntervalTrigger(minutes=5),
        id="vector_retry",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started. Daily digest at %02d:%02d UTC.",
        settings.DAILY_DIGEST_HOUR,
        settings.DAILY_DIGEST_MINUTE,
    )
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
