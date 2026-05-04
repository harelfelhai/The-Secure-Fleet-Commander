import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_broadcaster
from app.models import Agent, FlightSession, GpsBreadcrumb
from app.schemas.agents import AgentListResponse, AgentResponse, BreadcrumbResponse, SessionResponse
from app.schemas.messages import AgentStatus
from app.services.broadcaster import FleetBroadcaster

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Broadcaster = Annotated[FleetBroadcaster, Depends(get_broadcaster)]


@router.get("/snapshot", response_model=list[AgentStatus])
async def fleet_snapshot(broadcaster: Broadcaster) -> list[AgentStatus]:
    """Return the current in-memory fleet state for all connected agents.

    Called by the frontend immediately after reconnecting so the map is
    up-to-date without waiting for the next FLEET_UPDATE broadcast.
    """
    return broadcaster.get_snapshot()


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


@router.get("/{agent_id}/breadcrumbs", response_model=list[BreadcrumbResponse])
async def get_agent_breadcrumbs(agent_id: uuid.UUID, db: DbSession) -> list[BreadcrumbResponse]:
    """Return all breadcrumbs for the agent's most recent flight session, ordered
    chronologically ascending.  Used by the frontend Replay feature to load the
    full mission trail on demand.
    """
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Find the most recent session (active or last completed)
    session_result = await db.execute(
        select(FlightSession)
        .where(FlightSession.agent_id == agent_id)
        .order_by(FlightSession.started_at.desc())
        .limit(1)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return []

    result = await db.execute(
        select(GpsBreadcrumb)
        .where(
            GpsBreadcrumb.agent_id == agent_id,
            GpsBreadcrumb.session_id == session.id,
        )
        .order_by(GpsBreadcrumb.recorded_at.asc())
    )
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
