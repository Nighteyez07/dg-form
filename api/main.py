import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import upload as upload_router
from routers import analyze as analyze_router
from routers.upload import start_eviction_task

# NOTE: Set PYTHONDONTWRITEBYTECODE=1 and PYTHONUNBUFFERED=1 in the container
#       environment (Dockerfile / docker-compose.yml), not here.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_TMP_DIR = Path("/tmp/dg-form")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("dg-form API starting up; tmp dir: %s", _TMP_DIR)
    await start_eviction_task()
    yield
    logger.info("dg-form API shutting down")


def create_app() -> FastAPI:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    app = FastAPI(
        title="dg-form API",
        version="0.1.0",
        description="Disc golf throw form critique API",
        lifespan=_lifespan,
        docs_url="/docs" if ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if ENVIRONMENT == "development" else None,
        openapi_url="/openapi.json" if ENVIRONMENT == "development" else None,
    )

    cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.include_router(upload_router.router, prefix="/api")
    app.include_router(analyze_router.router, prefix="/api")

    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
