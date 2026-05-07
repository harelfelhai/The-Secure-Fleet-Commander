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
from app.models import Agent, CommandLog, FlightSession, Gateway
from app.schemas.messages import (
    AckFrame,
    CommandError,
    CommandSent,
    FrontendCommand,
    LinkStatusMessage,
    TelemetryFrame,
)
from app.services.broadcaster import FleetBroadcaster
from app.services.command_service import CommandService
from app.services.connection_manager import frontend_manager, gateway_manager
from app.services.ingestion import IngestionContext, IngestionService
from app.services.rules_engine import RulesEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _upsert_gateway(db: AsyncSession, hardware_id: str) -> Gateway:
    """Return existing Gateway or create a new one; always refreshes last_connected_at."""
    result = await db.execute(select(Gateway).where(Gateway.hardware_id == hardware_id))
    gw = result.scalar_one_or_none()
    if gw is None:
        gw = Gateway(
            hardware_id=hardware_id,
            display_name=hardware_id,
            last_connected_at=datetime.now(UTC),
        )
        db.add(gw)
    else:
        gw.last_connected_at = datetime.now(UTC)
    await db.flush()
    return gw


async def _upsert_agent(
    db: AsyncSession, hardware_id: str, gateway_id: uuid.UUID | None = None
) -> Agent:
    """Return existing Agent or create a new one for this hardware_id."""
    result = await db.execute(select(Agent).where(Agent.hardware_id == hardware_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(
            hardware_id=hardware_id,
            display_name=hardware_id,  # default; operator can rename via API later
            gateway_id=gateway_id,
            link_status="LINKED",
        )
        db.add(agent)
    else:
        agent.gateway_id = gateway_id
        agent.link_status = "LINKED"
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


async def _handle_ack(ack: AckFrame) -> None:
    """Persist ACK result — update CommandLog status and acked_at."""
    try:
        command_id = uuid.UUID(ack.command_id)
    except ValueError:
        logger.warning("ACK with invalid command_id format: %s", ack.command_id)
        return

    async with AsyncSessionLocal() as db:
        async with db.begin():
            result = await db.execute(select(CommandLog).where(CommandLog.id == command_id))
            log = result.scalar_one_or_none()
            if log is None:
                logger.warning("ACK for unknown command_id %s", ack.command_id)
                return
            log.status = ack.status
            log.acked_at = ack.acked_at

    logger.info("Command %s → %s", ack.command_id, ack.status)


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

    # ── 2. Upsert gateway + agent + open session (short-lived setup transaction)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            gateway = await _upsert_gateway(db, hardware_id)
            agent = await _upsert_agent(db, hardware_id, gateway_id=gateway.id)
            session = await _open_session(db, agent.id)

    gateway_id = gateway.id
    agent_id = agent.id
    agent_display_name = agent.display_name
    session_id = session.id
    ingest_ctx = IngestionContext(
        session_id=session_id,
        agent_id=agent_id,
        display_name=agent_display_name,
        gateway_hardware_id=hardware_id,
        device_type=agent.device_type,
        session_started_at=session.started_at,
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
    logger.info(
        "Gateway ready: hardware_id=%s gateway_id=%s agent_id=%s",
        hardware_id,
        gateway_id,
        agent_id,
    )

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
            ingest_svc = IngestionService(
                db,
                rules_engine,
                broadcaster,
                persist_interval_seconds=settings.persist_interval_seconds,
            )
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

                    # Anti-spoofing: agent_id in frame must match the authenticated hardware_id.
                    # The gateway sets agent_id to its hardware_id string, not the DB UUID.
                    if frame.agent_id != hardware_id:
                        logger.error(
                            "agent_id mismatch from %s: got %s expected %s",
                            hardware_id,
                            frame.agent_id,
                            hardware_id,
                        )
                        await websocket.close(code=4003, reason="agent_id mismatch")
                        return

                    try:
                        await ingest_svc.ingest(frame, ingest_ctx)
                    except Exception:
                        logger.error("Ingest failed for agent %s", agent_id, exc_info=True)

                elif msg_type == "LINK_STATUS":
                    try:
                        link_msg = LinkStatusMessage.model_validate(data)
                    except ValidationError as exc:
                        logger.warning(
                            "LINK_STATUS validation failed from %s: %s", hardware_id, exc
                        )
                        continue

                    broadcaster.mark_link_status(link_msg.agent_id, link_msg.link_status)
                    logger.info(
                        "Link status update: gateway=%s agent=%s status=%s",
                        hardware_id,
                        link_msg.agent_id,
                        link_msg.link_status,
                    )
                    try:
                        await broadcaster.broadcast_fleet_update()
                    except Exception:
                        logger.error("Fleet broadcast after LINK_STATUS failed", exc_info=True)

                elif msg_type == "ACK":
                    try:
                        ack = AckFrame.model_validate(data)
                    except ValidationError as exc:
                        logger.warning("ACK validation failed from %s: %s", hardware_id, exc)
                        continue
                    try:
                        await _handle_ack(ack)
                    except Exception:
                        logger.error(
                            "ACK handling failed for command %s",
                            data.get("command_id"),
                            exc_info=True,
                        )

                else:
                    logger.debug("Unknown msg_type '%s' from %s", msg_type, hardware_id)

    except WebSocketDisconnect:
        logger.info("Gateway disconnected: %s", hardware_id)
    finally:
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
        gateway_manager.disconnect(hardware_id)
        rules_engine.clear_agent_state(str(agent_id))
        # Cloud disconnect: gateway WS dropped → all agents on this gateway lose cloud link
        broadcaster.mark_cloud_lost(hardware_id)
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
    await websocket.accept()
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
                try:
                    cmd = FrontendCommand.model_validate(data)
                except ValidationError as exc:
                    await websocket.send_text(
                        CommandError(
                            agent_id=data.get("agent_id"), reason=f"invalid command: {exc}"
                        ).model_dump_json()
                    )
                    continue

                try:
                    async with AsyncSessionLocal() as db:
                        svc = CommandService(db=db, gw_manager=gateway_manager)
                        log, error = await svc.dispatch(cmd)
                except Exception:
                    logger.error(
                        "Command dispatch failed for agent %s",
                        data.get("agent_id"),
                        exc_info=True,
                    )
                    await websocket.send_text(
                        CommandError(
                            agent_id=data.get("agent_id"), reason="internal error"
                        ).model_dump_json()
                    )
                    continue

                if error:
                    await websocket.send_text(
                        CommandError(agent_id=cmd.agent_id, reason=error).model_dump_json()
                    )
                else:
                    await websocket.send_text(
                        CommandSent(
                            command_id=str(log.id),
                            agent_id=cmd.agent_id,
                            command_type=log.command_type,  # type: ignore[arg-type]
                            issued_at=log.issued_at,
                        ).model_dump_json()
                    )
            else:
                logger.debug("Unknown frontend msg_type: %s", msg_type)

    except WebSocketDisconnect:
        logger.info("Frontend client disconnected")
    finally:
        frontend_manager.disconnect(websocket)
