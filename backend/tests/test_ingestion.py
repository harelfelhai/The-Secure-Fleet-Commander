"""
Unit tests for IngestionService.
All external dependencies (DB, rules engine, broadcaster) are replaced with mocks.
"""

import uuid
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

CTX = IngestionContext(session_id=SESSION_ID, agent_id=AGENT_ID, display_name="Alpha-1")


def make_service():
    db = MagicMock()
    # Simulate 'async with db.begin()' as a no-op async context manager
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

    svc = IngestionService(db=db, rules_engine=rules, broadcaster=broadcaster)
    return svc, db, rules, broadcaster


@pytest.mark.asyncio
async def test_normal_ingest_persists_and_broadcasts():
    svc, db, rules, broadcaster = make_service()
    await svc.ingest(FRAME, CTX)

    db.add.assert_called_once()  # GpsBreadcrumb added
    db.execute.assert_called_once()  # Agent.last_seen_at updated
    rules.evaluate.assert_called_once_with(FRAME)
    broadcaster.update_agent.assert_called_once()
    broadcaster.broadcast_fleet_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_geofence_alert_persists_violation_log_and_broadcasts():
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

    await svc.ingest(FRAME, CTX)

    # db.add called twice: once for breadcrumb, once for violation log
    assert db.add.call_count == 2
    broadcaster.broadcast_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_battery_alert_broadcasts_but_does_not_persist():
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

    await svc.ingest(FRAME, CTX)

    # db.add called only once (breadcrumb — no violation log for LOW_BATTERY)
    assert db.add.call_count == 1
    broadcaster.broadcast_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_rules_engine_error_does_not_prevent_fleet_update():
    svc, db, rules, broadcaster = make_service()
    rules.evaluate = MagicMock(side_effect=RuntimeError("boom"))

    await svc.ingest(FRAME, CTX)

    # Fleet update still sent despite rules engine failure
    broadcaster.broadcast_fleet_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcaster_error_does_not_propagate():
    svc, db, rules, broadcaster = make_service()
    broadcaster.broadcast_fleet_update = AsyncMock(side_effect=RuntimeError("network error"))

    # Should not raise
    await svc.ingest(FRAME, CTX)
