"""
IngestionService — orchestrates the full telemetry ingest pipeline for one frame.

Step order (per technical plan):
  1. Persist breadcrumb + update Agent.last_seen_at  (single transaction)
  2. Run rules engine                                 (pure, no I/O)
  3. For GEOFENCE_VIOLATION alerts: persist ViolationLog (separate transaction)
  4. Broadcast all alerts to frontend
  5. Update broadcaster state and fan-out FLEET_UPDATE

If persistence (step 1) fails, an exception propagates to the caller.
If the rules engine or broadcasting fails, it is logged but does not affect persistence.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, GpsBreadcrumb, ViolationLog
from app.schemas.messages import TelemetryFrame
from app.services.broadcaster import FleetBroadcaster
from app.services.rules_engine import InternalAlert, RulesEngine

logger = logging.getLogger(__name__)


@dataclass
class IngestionContext:
    session_id: UUID
    agent_id: UUID
    display_name: str


class IngestionService:
    def __init__(
        self,
        db: AsyncSession,
        rules_engine: RulesEngine,
        broadcaster: FleetBroadcaster,
    ) -> None:
        self._db = db
        self._rules = rules_engine
        self._broadcaster = broadcaster

    async def ingest(self, frame: TelemetryFrame, ctx: IngestionContext) -> None:
        # ── 1. Persist ────────────────────────────────────────────────────────
        await self._persist(frame, ctx)

        # ── 2. Evaluate rules ─────────────────────────────────────────────────
        try:
            alerts = self._rules.evaluate(frame)
        except Exception:
            logger.error("Rules engine failed for agent %s", ctx.agent_id, exc_info=True)
            alerts = []

        # ── 3 & 4. Handle alerts ──────────────────────────────────────────────
        for alert in alerts:
            await self._handle_alert(alert, frame, ctx)

        # ── 5. Fan-out FLEET_UPDATE ───────────────────────────────────────────
        self._broadcaster.update_agent(
            agent_id=str(ctx.agent_id),
            display_name=ctx.display_name,
            frame_data={
                "latitude": frame.latitude,
                "longitude": frame.longitude,
                "altitude_m": frame.altitude_m,
                "battery_pct": frame.battery_pct,
                "last_seen_at": frame.timestamp,
            },
        )
        try:
            await self._broadcaster.broadcast_fleet_update()
        except Exception:
            logger.error("Fleet broadcast failed", exc_info=True)

    async def _persist(self, frame: TelemetryFrame, ctx: IngestionContext) -> None:
        async with self._db.begin():
            self._db.add(
                GpsBreadcrumb(
                    session_id=ctx.session_id,
                    agent_id=ctx.agent_id,
                    recorded_at=frame.timestamp,
                    latitude=frame.latitude,
                    longitude=frame.longitude,
                    altitude_m=frame.altitude_m,
                    battery_pct=frame.battery_pct,
                )
            )
            await self._db.execute(
                update(Agent).where(Agent.id == ctx.agent_id).values(last_seen_at=frame.timestamp)
            )

    async def _handle_alert(
        self,
        alert: InternalAlert,
        frame: TelemetryFrame,
        ctx: IngestionContext,
    ) -> None:
        if alert.alert_type == "GEOFENCE_VIOLATION":
            try:
                async with self._db.begin():
                    self._db.add(
                        ViolationLog(
                            agent_id=ctx.agent_id,
                            zone_name=alert.context["zone_name"],
                            latitude=frame.latitude,
                            longitude=frame.longitude,
                            detected_at=datetime.now(UTC),
                        )
                    )
            except Exception:
                logger.error(
                    "Failed to persist ViolationLog for agent %s", ctx.agent_id, exc_info=True
                )

        try:
            await self._broadcaster.broadcast_alert(alert, str(ctx.agent_id))
        except Exception:
            logger.error("Alert broadcast failed for agent %s", ctx.agent_id, exc_info=True)
