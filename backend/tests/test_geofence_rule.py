"""
Unit tests for GeofenceRule.
Zone evaluator is patched so the rule logic is tested in isolation.
"""

from unittest.mock import patch

import pytest

from app.schemas.messages import TelemetryFrame
from app.services.rules.geofence import GeofenceRule
from app.services.rules_engine import RuleContext

FRAME_BASE = dict(
    msg_type="TELEMETRY",
    schema_version="1.0",
    agent_id="550e8400-e29b-41d4-a716-446655440000",
    timestamp="2026-05-01T10:00:00Z",
    latitude=32.09,
    longitude=34.78,
    altitude_m=50.0,
    battery_pct=80.0,
)


def make_frame(**kwargs) -> TelemetryFrame:
    return TelemetryFrame.model_validate({**FRAME_BASE, **kwargs})


@pytest.fixture
def rule():
    return GeofenceRule()


@pytest.fixture
def ctx():
    return RuleContext()


def test_entry_fires_alert(rule, ctx):
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(True, "Zone Alpha"),
    ):
        alerts = rule.evaluate(make_frame(), ctx)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "GEOFENCE_VIOLATION"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].context["zone_name"] == "Zone Alpha"
    assert "Zone Alpha" in ctx.active_zones


def test_sustained_inside_zone_suppressed(rule, ctx):
    ctx.active_zones.add("Zone Alpha")  # already inside
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(True, "Zone Alpha"),
    ):
        alerts = rule.evaluate(make_frame(), ctx)

    assert alerts == []


def test_exit_clears_active_zones(rule, ctx):
    ctx.active_zones.add("Zone Alpha")
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(False, None),
    ):
        alerts = rule.evaluate(make_frame(), ctx)

    assert alerts == []
    assert ctx.active_zones == set()


def test_reentry_after_exit_fires_again(rule, ctx):
    # Enter
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(True, "Zone Alpha"),
    ):
        rule.evaluate(make_frame(), ctx)

    # Exit
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(False, None),
    ):
        rule.evaluate(make_frame(), ctx)

    # Re-enter
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(True, "Zone Alpha"),
    ):
        alerts = rule.evaluate(make_frame(), ctx)

    assert len(alerts) == 1


def test_no_zones_loaded_no_alert(rule, ctx):
    with patch(
        "app.services.rules.geofence.zone_evaluator.evaluate",
        return_value=(False, None),
    ):
        alerts = rule.evaluate(make_frame(), ctx)

    assert alerts == []
