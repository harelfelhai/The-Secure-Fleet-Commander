import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, FlightSession, GpsBreadcrumb
from app.schemas.agents import AgentListResponse, AgentResponse, BreadcrumbResponse, SessionResponse

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=AgentListResponse)
async def list_agents(db: DbSession) -> AgentListResponse:
    result = await db.execute(select(Agent).order_by(Agent.registered_at.desc()))
    agents = result.scalars().all()
    return AgentListResponse(
        agents=[AgentResponse.model_validate(a) for a in agents],
        total=len(agents),
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: DbSession) -> AgentResponse:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/path", response_model=list[BreadcrumbResponse])
async def get_agent_path(
    agent_id: uuid.UUID,
    db: DbSession,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    limit: int = Query(default=1000, le=5000),
) -> list[BreadcrumbResponse]:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stmt = (
        select(GpsBreadcrumb)
        .where(GpsBreadcrumb.agent_id == agent_id)
        .order_by(GpsBreadcrumb.recorded_at.desc())
        .limit(limit)
    )
    if from_time:
        stmt = stmt.where(GpsBreadcrumb.recorded_at >= from_time)
    if to_time:
        stmt = stmt.where(GpsBreadcrumb.recorded_at <= to_time)

    result = await db.execute(stmt)
    return [BreadcrumbResponse.model_validate(b) for b in result.scalars().all()]


@router.get("/{agent_id}/sessions", response_model=list[SessionResponse])
async def get_agent_sessions(agent_id: uuid.UUID, db: DbSession) -> list[SessionResponse]:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(FlightSession)
        .where(FlightSession.agent_id == agent_id)
        .order_by(FlightSession.started_at.desc())
    )
    return [SessionResponse.model_validate(s) for s in result.scalars().all()]
