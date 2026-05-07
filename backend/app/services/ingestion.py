"""
IngestionService — orchestrates the full telemetry ingest pipeline for one frame.

Step order:
  1. Evaluate rules engine   (always — pure, no I/O; dedup state must stay current)
  2. Handle alerts           (always — ViolationLog for geofence, broadcast all alerts)
  3. Broadcast FLEET_UPDATE  (always — every frame reaches the frontend for smooth UI)
  4. Persist breadcrumb      (conditional — see below)

Persistence throttle (step 4):
  A GpsBreadcrumb is written to the DB only if ANY of:
    a) No breadcrumb has been written yet this session (first frame)
    b) At least `persist_interval_seconds` have elapsed since the last write
    c) The rules engine raised at least one alert on this frame
       (alert frames are always persisted as evidence, regardless of interval)

  Throttle uses event time (frame.timestamp) for all elapsed calculations — both
  live and backfill paths.  Using the server clock for backfill frames would cause
  the entire buffer replay (which arrives as a rapid burst) to be collapsed to a
  single breadcrumb because server-side elapsed between frames is near zero.

  Agent.last_seen_at is updated in the same transaction as the breadcrumb.

If the breadcrumb write fails, an exception propagates to the caller.
All other failures (rules, alerts, broadcast) are logged and swallowed.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, GpsBreadcrumb, ViolationLog
from app.schemas.messages import TelemetryFrame
from app.services.broadcaster import FleetBroadcaster
from app.services.rules_engine import InternalAlert, RulesEngine

logger = logging.getLogger(__name__)


def _event_elapsed(event_time: datetime, last: datetime | None) -> float:
    """Seconds of drone-time elapsed since the last persisted frame.

    Returns inf when last is None (first frame of a session) so the caller
    always persists the first frame regardless of the configured interval.
    """
    return float("inf") if last is None else (event_time - last).total_seconds()


@dataclass
class IngestionContext:
    session_id: UUID
    agent_id: UUID
    display_name: str
    gateway_hardware_id: str | None = None
    device_type: str = "DRONE"
    session_started_at: datetime | None = None
    last_persisted_at: datetime | None = field(default=None, compare=False)


_SILENCE_THRESHOLD = 5.0  # seconds — gap larger than this is logged as a segment boundary


class IngestionService:
    def __init__(
        self,
        db: AsyncSession,
        rules_engine: RulesEngine,
        broadcaster: FleetBroadcaster,
        persist_interval_seconds: float = 2.0,
    ) -> None:
        self._db = db
        self._rules = rules_engine
        self._broadcaster = broadcaster
        self._persist_interval = persist_interval_seconds

    async def ingest(self, frame: TelemetryFrame, ctx: IngestionContext) -> None:
        # ── Backfill fast-path ────────────────────────────────────────────────
        # Frames replayed from the offline buffer skip the rules engine and
        # broadcaster so stale data never overwrites the live UI state.
        if frame.is_backfill:
            await self._ingest_backfill(frame, ctx)
            return

        # ── 1. Evaluate rules (always) ────────────────────────────────────────
        try:
            alerts = self._rules.evaluate(frame)
        except Exception:
            logger.error("Rules engine failed for agent %s", ctx.agent_id, exc_info=True)
            alerts = []

        # ── 2. Handle alerts (always) ─────────────────────────────────────────
        for alert in alerts:
            await self._handle_alert(alert, frame, ctx)

        # ── 3. Fan-out FLEET_UPDATE (always) ──────────────────────────────────
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
            gateway_hardware_id=ctx.gateway_hardware_id,
            device_type=ctx.device_type,  # type: ignore[arg-type]
            mission_start_at=ctx.session_started_at,
        )
        try:
            await self._broadcaster.broadcast_fleet_update()
        except Exception:
            logger.error("Fleet broadcast failed", exc_info=True)

        # ── 4. Conditionally persist breadcrumb ───────────────────────────────
        # Use event time (frame.timestamp) so the throttle measures drone time,
        # not server arrival time.  For live frames the two clocks are within
        # milliseconds of each other; the semantic is identical.  Keeping a
        # single clock reference also prevents sign-flip bugs when last_persisted_at
        # was written by the live path and is then read by the backfill path.
        elapsed = _event_elapsed(frame.timestamp, ctx.last_persisted_at)
        if elapsed >= self._persist_interval or bool(alerts):
            if ctx.last_persisted_at is None:
                logger.info("Segment start for agent %s (new session)", ctx.agent_id)
            elif elapsed >= _SILENCE_THRESHOLD:
                logger.info("Segment boundary for agent %s (silence=%.1fs)", ctx.agent_id, elapsed)
            await self._persist(frame, ctx)
            ctx.last_persisted_at = frame.timestamp
            logger.debug(
                "Persisted breadcrumb for agent %s (elapsed=%.2fs alerts=%d)",
                ctx.agent_id,
                elapsed,
                len(alerts),
            )
        else:
            logger.debug(
                "Skipped breadcrumb for agent %s (elapsed=%.2fs < %.2fs)",
                ctx.agent_id,
                elapsed,
                self._persist_interval,
            )

    async def _ingest_backfill(self, frame: TelemetryFrame, ctx: IngestionContext) -> None:
        """
        Persist a backfill breadcrumb only — skip rules, alerts, and broadcast.

        Throttle is measured in event time (frame.timestamp) so that a buffer
        replay arriving as a rapid server-side burst still produces one breadcrumb
        per persist_interval of *original drone time*.  Without this, hundreds of
        frames delivered within the same server-clock second would collapse to a
        single row, discarding an hour of position history.
        """
        elapsed = _event_elapsed(frame.timestamp, ctx.last_persisted_at)
        if elapsed >= self._persist_interval:
            await self._persist(frame, ctx)
            ctx.last_persisted_at = frame.timestamp
            logger.debug(
                "Backfill breadcrumb persisted for agent %s (event_elapsed=%.2fs)",
                ctx.agent_id,
                elapsed,
            )
        else:
            logger.debug(
                "Backfill breadcrumb skipped for agent %s (event_elapsed=%.2fs < %.2fs)",
                ctx.agent_id,
                elapsed,
                self._persist_interval,
            )

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
            if not frame.is_backfill:
                # Backfill frames are historical — don't roll back last_seen_at
                await self._db.execute(
                    update(Agent)
                    .where(Agent.id == ctx.agent_id)
                    .values(last_seen_at=frame.timestamp)
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
