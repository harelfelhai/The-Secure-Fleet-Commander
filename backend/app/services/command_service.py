"""
CommandService — handles the full dispatch lifecycle for a single emergency command.

Steps:
  1. Verify agent exists in DB.
  2. Write CommandLog(status=SENT) in a committed transaction.
  3. Check whether the agent's gateway WebSocket is live.
  4a. Connected: serialise CommandDispatch and push over the WS.
  4b. Offline or send failed: update CommandLog(status=FAILED) and return an error string.

Returns (CommandLog | None, error_message).
error_message is "" on success; human-readable on failure.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, CommandLog
from app.schemas.messages import CommandDispatch, FrontendCommand
from app.services.connection_manager import GatewayConnectionManager

logger = logging.getLogger(__name__)


class CommandService:
    def __init__(self, db: AsyncSession, gw_manager: GatewayConnectionManager) -> None:
        self._db = db
        self._gw = gw_manager

    async def dispatch(self, cmd: FrontendCommand) -> tuple[CommandLog | None, str]:
        issued_at = datetime.now(UTC)
        command_id = uuid.uuid4()

        # ── 1 & 2. Verify agent + write CommandLog in one transaction ─────────
        async with self._db.begin():
            result = await self._db.execute(
                select(Agent).where(Agent.id == uuid.UUID(cmd.agent_id))
            )
            agent = result.scalar_one_or_none()
            if agent is None:
                return None, "agent not found"

            log = CommandLog(
                id=command_id,
                agent_id=agent.id,
                command_type=cmd.command_type,
                payload={},
                status="SENT",
                issued_at=issued_at,
            )
            self._db.add(log)
        # Transaction committed; CommandLog(status=SENT) is durable.

        # ── 3. Check gateway connection ───────────────────────────────────────
        if not self._gw.is_connected(agent.hardware_id):
            await self._mark_failed(command_id)
            log.status = "FAILED"
            return log, "gateway offline"

        # ── 4. Send CommandDispatch over the live gateway WS ──────────────────
        dispatch_msg = CommandDispatch(
            command_id=str(command_id),
            command_type=cmd.command_type,
            issued_at=issued_at,
        )
        sent = await self._gw.send(agent.hardware_id, dispatch_msg.model_dump_json())
        if not sent:
            await self._mark_failed(command_id)
            log.status = "FAILED"
            return log, "delivery failed"

        logger.info(
            "Command dispatched: id=%s type=%s agent=%s",
            command_id,
            cmd.command_type,
            cmd.agent_id,
        )
        return log, ""

    async def _mark_failed(self, command_id: uuid.UUID) -> None:
        async with self._db.begin():
            result = await self._db.execute(select(CommandLog).where(CommandLog.id == command_id))
            log = result.scalar_one_or_none()
            if log:
                log.status = "FAILED"
