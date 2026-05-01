import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
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
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
