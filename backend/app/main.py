import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.routers import agents, auth, violations, ws, zones
from app.services.zone_evaluator import load_zones

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if settings.debug else logging.INFO
    )
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Fleet Commander Backend")
    load_zones(settings.zones_config_path)
    yield
    logger.info("Shutting down Fleet Commander Backend")


app = FastAPI(
    title="Fleet Commander",
    version="0.1.0",
    description="Secure Command & Control backend for autonomous agent fleets.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(zones.router)
app.include_router(violations.router)
app.include_router(auth.router)
app.include_router(ws.router)


@app.get("/health", tags=["ops"])
async def health(response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — health probe surfaces all DB failures
        logger.warning("health_check_db_failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "version": "0.1.0", "database": "unreachable"}
    return {"status": "ok", "version": "0.1.0", "database": "ok"}
