"""
Unit tests for IngestionService.
All external dependencies (DB, rules engine, broadcaster) are replaced with mocks.
"""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.messages import TelemetryFrame
from app.services.ingestion import IngestionContext, IngestionService
from app.services.rules_engine import InternalAlert

AGENT_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()

FRAME = TelemetryFrame.model_validate(
    dict(
        msg_type="TELEMETRY",
        schema_version="1.0",
        agent_id=str(AGENT_ID),
        timestamp="2026-05-01T10:00:00Z",
        latitude=32.09,
        longitude=34.78,
        altitude_m=50.0,
        battery_pct=80.0,
    )
)


def make_service(persist_interval: float = 2.0):
    db = MagicMock()
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=begin_ctx)
    db.add = MagicMock()
    db.execute = AsyncMock()

    rules = MagicMock()
    rules.evaluate = MagicMock(return_value=[])

    broadcaster = MagicMock()
    broadcaster.update_agent = MagicMock()
    broadcaster.broadcast_fleet_update = AsyncMock()
    broadcaster.broadcast_alert = AsyncMock()

    svc = IngestionService(
        db=db,
        rules_engine=rules,
        broadcaster=broadcaster,
        persist_interval_seconds=persist_interval,
    )
    return svc, db, rules, broadcaster


def fresh_ctx() -> IngestionContext:
    return IngestionContext(session_id=SESSION_ID, agent_id=AGENT_ID, display_name="Alpha-1")


# ── Throttle logic ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_session_first_frame_always_persisted():
    """
    Case 1: New session / reconnect.
    IngestionContext is created fresh (last_persisted_at=None) on every gateway WS connect.
    The very first frame must be written to DB to anchor the flight path start.
    """
    svc, db, rules, broadcaster = make_service()
    ctx = fresh_ctx()
    assert ctx.last_persisted_at is None  # fresh session, no prior persists

    await svc.ingest(FRAME, ctx)

    db.add.assert_called_once()
    db.execute.assert_called_once()
    assert ctx.last_persisted_at is not None


@pytest.mark.asyncio
async def test_post_silence_recovery_frame_persisted():
    """
    Case 2: Post-silence recovery.
    If the gateway went quiet for longer than persist_interval, the next frame that
    arrives must be persisted immediately to mark the start of the new movement segment.
    Elapsed since last persist (5 s) >> persist_interval (2 s) → always persisted.
    """
    svc, db, rules, broadcaster = make_service(persist_interval=2.0)
    ctx = fresh_ctx()
    ctx.last_persisted_at = FRAME.timestamp - timedelta(seconds=5.0)  # 5 s silence in event time

    await svc.ingest(FRAME, ctx)

    db.add.assert_called_once()
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_short_gap_within_interval_not_persisted():
    """
    A brief packet drop shorter than the persist interval is NOT treated as a
    segment boundary — it is just a normal skipped frame.
    """
    svc, db, rules, broadcaster = make_service(persist_interval=2.0)
    ctx = fresh_ctx()
    ctx.last_persisted_at = FRAME.timestamp - timedelta(seconds=0.5)

    await svc.ingest(FRAME, ctx)

    db.add.assert_not_called()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_frame_after_interval_is_persisted():
    svc, db, rules, broadcaster = make_service(persist_interval=2.0)
    ctx = fresh_ctx()
    ctx.last_persisted_at = FRAME.timestamp - timedelta(seconds=3.0)

    await svc.ingest(FRAME, ctx)

    db.add.assert_called_once()
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_alert_frame_persisted_regardless_of_interval():
    svc, db, rules, broadcaster = make_service(persist_interval=2.0)
    rules.evaluate = MagicMock(
        return_value=[
            InternalAlert(
                "LOW_BATTERY",
                "WARNING",
                "Battery low",
                {"battery_pct": 15.0, "threshold_pct": 20.0},
            )
        ]
    )
    ctx = fresh_ctx()
    ctx.last_persisted_at = FRAME.timestamp - timedelta(seconds=0.5)  # within interval

    await svc.ingest(FRAME, ctx)

    db.add.assert_called_once()  # alert overrides throttle


@pytest.mark.asyncio
async def test_broadcast_always_happens_even_when_not_persisting():
    svc, db, rules, broadcaster = make_service()
    ctx = fresh_ctx()
    ctx.last_persisted_at = FRAME.timestamp  # just persisted → elapsed=0 → no persist this frame

    await svc.ingest(FRAME, ctx)

    db.add.assert_not_called()
    broadcaster.update_agent.assert_called_once()
    broadcaster.broadcast_fleet_update.assert_awaited_once()


# ── Alert handling ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_geofence_alert_persists_violation_log_and_breadcrumb():
    svc, db, rules, broadcaster = make_service()
    rules.evaluate = MagicMock(
        return_value=[
            InternalAlert(
                alert_type="GEOFENCE_VIOLATION",
                severity="CRITICAL",
                message="Zone breach",
                context={"zone_name": "Test Zone"},
            )
        ]
    )
    ctx = fresh_ctx()
    await svc.ingest(FRAME, ctx)

    # ViolationLog (via _handle_alert) + GpsBreadcrumb (alert-triggered persist)
    assert db.add.call_count == 2
    broadcaster.broadcast_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_battery_alert_broadcasts_and_persists_breadcrumb():
    svc, db, rules, broadcaster = make_service()
    rules.evaluate = MagicMock(
        return_value=[
            InternalAlert(
                alert_type="LOW_BATTERY",
                severity="WARNING",
                message="Battery low: 15.0%",
                context={"battery_pct": 15.0, "threshold_pct": 20.0},
            )
        ]
    )
    ctx = fresh_ctx()
    await svc.ingest(FRAME, ctx)

    # Breadcrumb persisted (alert-triggered), no ViolationLog for LOW_BATTERY
    assert db.add.call_count == 1
    broadcaster.broadcast_alert.assert_awaited_once()


# ── Error isolation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rules_engine_error_does_not_prevent_fleet_update():
    svc, db, rules, broadcaster = make_service()
    rules.evaluate = MagicMock(side_effect=RuntimeError("boom"))

    ctx = fresh_ctx()
    await svc.ingest(FRAME, ctx)

    broadcaster.broadcast_fleet_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcaster_error_does_not_propagate():
    svc, db, rules, broadcaster = make_service()
    broadcaster.broadcast_fleet_update = AsyncMock(side_effect=RuntimeError("network error"))

    ctx = fresh_ctx()
    await svc.ingest(FRAME, ctx)  # must not raise
