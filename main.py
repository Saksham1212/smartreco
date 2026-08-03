"""SmartReco — FastAPI entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import vector_store
from config import settings
from database import AsyncSessionLocal, create_all_tables
from scheduler import shutdown_scheduler, start_scheduler
from seed import seed_admin_if_missing, seed_products_if_empty
from templating import templates

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smartreco.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.MESH_API_KEY:
        raise RuntimeError(
            "MESH_API_KEY is not set. Copy .env.example to .env and set your Mesh API key."
        )

    await create_all_tables()
    logger.info("Database tables ready")

    async with AsyncSessionLocal() as db:
        await seed_products_if_empty(db)
        await seed_admin_if_missing(db)

    vector_store.init_vector_store()
    logger.info("ChromaDB vector store ready")

    start_scheduler()

    logger.info("SmartReco startup complete — listening for requests")
    yield

    shutdown_scheduler()
    logger.info("SmartReco shutdown complete")


app = FastAPI(title="SmartReco", debug=settings.DEBUG, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        detail = exc.detail
        if isinstance(detail, dict):
            body = detail
        else:
            body = {"error": str(detail), "detail": None}
        return JSONResponse(status_code=exc.status_code, content=body)

    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)

    template_name = "404.html" if exc.status_code == 404 else "403.html"
    return templates.TemplateResponse(
        template_name, {"request": request, "user": None}, status_code=exc.status_code
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500, content={"error": "Internal server error", "detail": str(exc) if settings.DEBUG else None}
        )
    return templates.TemplateResponse(
        "500.html", {"request": request, "user": None}, status_code=500
    )


from routers import admin, auth, events, pages, products, recommendations  # noqa: E402

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(events.router)
app.include_router(recommendations.router)
app.include_router(admin.router)
app.include_router(pages.router)
