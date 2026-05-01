import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ViolationLog

router = APIRouter(prefix="/api/v1/violations", tags=["violations"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ViolationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    zone_name: str
    latitude: float
    longitude: float
    detected_at: datetime


@router.get("", response_model=list[ViolationResponse])
async def list_violations(
    db: DbSession,
    agent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=500),
) -> list[ViolationResponse]:
    stmt = select(ViolationLog).order_by(ViolationLog.detected_at.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(ViolationLog.agent_id == agent_id)
    result = await db.execute(stmt)
    return [ViolationResponse.model_validate(v) for v in result.scalars().all()]
