"""
WebSocket routers.

/ws/gateway/{hardware_id}  — Gateway connection (ingest + command delivery)
/ws/fleet/live             — Frontend connection (fleet updates + command dispatch)
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.ws_auth import authenticate_gateway_ws
from app.database import AsyncSessionLocal
from app.dependencies import get_broadcaster, get_rules_engine
from app.models import Agent, FlightSession
from app.schemas.messages import TelemetryFrame
from app.services.broadcaster import FleetBroadcaster
from app.services.connection_manager import frontend_manager, gateway_manager
from app.services.ingestion import IngestionContext, IngestionService
from app.services.rules_engine import RulesEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _upsert_agent(db: AsyncSession, hardware_id: str) -> Agent:
    """Return existing Agent or create a new one for this hardware_id."""
    result = await db.execute(select(Agent).where(Agent.hardware_id == hardware_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(
            hardware_id=hardware_id,
            display_name=hardware_id,  # default; operator can rename via API later
        )
        db.add(agent)
        await db.flush()  # populate agent.id before we return
    return agent


async def _open_session(db: AsyncSession, agent_id: uuid.UUID) -> FlightSession:
    session = FlightSession(agent_id=agent_id, started_at=datetime.now(UTC))
    db.add(session)
    await db.flush()
    return session


async def _close_session(session_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(select(FlightSession).where(FlightSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.ended_at = datetime.now(UTC)


async def _watchdog(websocket: WebSocket, timeout: int, hardware_id: str) -> None:
    """Sleep for `timeout` seconds then close the connection (no frames received)."""
    await asyncio.sleep(timeout)
    logger.warning("Watchdog timeout for gateway %s — closing", hardware_id)
    try:
        await websocket.close(code=4408, reason="heartbeat timeout")
    except Exception:
        pass


# ── Gateway WebSocket ─────────────────────────────────────────────────────────


@router.websocket("/ws/gateway/{hardware_id}")
async def gateway_ws(
    websocket: WebSocket,
    hardware_id: str,
    rules_engine: RulesEngine = Depends(get_rules_engine),
    broadcaster: FleetBroadcaster = Depends(get_broadcaster),
) -> None:
    await websocket.accept()

    # ── 1. Authenticate ───────────────────────────────────────────────────────
    if not await authenticate_gateway_ws(websocket, hardware_id):
        return

    # ── 2. Upsert agent + open session (short-lived setup transaction) ────────
    async with AsyncSessionLocal() as db:
        async with db.begin():
            agent = await _upsert_agent(db, hardware_id)
            session = await _open_session(db, agent.id)

    agent_id = agent.id
    agent_display_name = agent.display_name
    session_id = session.id
    ingest_ctx = IngestionContext(
        session_id=session_id,
        agent_id=agent_id,
        display_name=agent_display_name,
    )

    # ── 3. Register + notify client ───────────────────────────────────────────
    await gateway_manager.connect(hardware_id, websocket)
    await websocket.send_json(
        {
            "msg_type": "READY",
            "agent_id": str(agent_id),
            "session_id": str(session_id),
        }
    )
    logger.info("Gateway ready: hardware_id=%s agent_id=%s", hardware_id, agent_id)

    # ── 4. Message loop ───────────────────────────────────────────────────────
    from app.config import settings  # local import avoids circular at module level

    watchdog_task: asyncio.Task | None = None

    def reset_watchdog() -> None:
        nonlocal watchdog_task
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
        watchdog_task = asyncio.create_task(
            _watchdog(websocket, settings.watchdog_timeout_seconds, hardware_id)
        )

    reset_watchdog()

    try:
        async with AsyncSessionLocal() as db:
            ingest_svc = IngestionService(db, rules_engine, broadcaster)
            while True:
                raw = await websocket.receive_text()
                reset_watchdog()

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.close(code=4003, reason="invalid json")
                    return

                msg_type = data.get("msg_type")

                if msg_type == "TELEMETRY":
                    try:
                        frame = TelemetryFrame.model_validate(data)
                    except ValidationError as exc:
                        logger.warning("Telemetry validation failed from %s: %s", hardware_id, exc)
                        continue  # drop single bad frame; keep connection open

                    # Anti-spoofing: agent_id in frame must match the authenticated agent
                    if frame.agent_id != str(agent_id):
                        logger.error(
                            "agent_id mismatch from %s: got %s expected %s",
                            hardware_id,
                            frame.agent_id,
                            agent_id,
                        )
                        await websocket.close(code=4003, reason="agent_id mismatch")
                        return

                    try:
                        await ingest_svc.ingest(frame, ingest_ctx)
                    except Exception:
                        logger.error("Ingest failed for agent %s", agent_id, exc_info=True)

                elif msg_type == "ACK":
                    # Milestone 2: update CommandLog status on ACK
                    pass

                else:
                    logger.debug("Unknown msg_type '%s' from %s", msg_type, hardware_id)

    except WebSocketDisconnect:
        logger.info("Gateway disconnected: %s", hardware_id)
    finally:
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
        gateway_manager.disconnect(hardware_id)
        rules_engine.clear_agent_state(str(agent_id))
        broadcaster.mark_stale(str(agent_id))
        await _close_session(session_id)
        try:
            await broadcaster.broadcast_fleet_update()
        except Exception:
            pass


# ── Frontend WebSocket ────────────────────────────────────────────────────────


@router.websocket("/ws/fleet/live")
async def fleet_ws(
    websocket: WebSocket,
    broadcaster: FleetBroadcaster = Depends(get_broadcaster),
) -> None:
    await frontend_manager.connect(websocket)

    # Send current fleet snapshot immediately so the frontend doesn't wait
    try:
        await broadcaster.broadcast_fleet_update()
    except Exception:
        logger.error("Initial fleet snapshot failed", exc_info=True)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("msg_type")

            if msg_type == "COMMAND":
                # Milestone 2: validate + dispatch GO_TO_WAYPOINT
                pass
            else:
                logger.debug("Unknown frontend msg_type: %s", msg_type)

    except WebSocketDisconnect:
        logger.info("Frontend client disconnected")
    finally:
        frontend_manager.disconnect(websocket)
