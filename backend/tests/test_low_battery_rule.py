"""
Unit tests for LowBatteryRule — edge-triggering and hysteresis.
"""

import pytest

from app.schemas.messages import TelemetryFrame
from app.services.rules.low_battery import LowBatteryRule
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


def make_frame(battery_pct: float) -> TelemetryFrame:
    return TelemetryFrame.model_validate({**FRAME_BASE, "battery_pct": battery_pct})


@pytest.fixture
def rule():
    return LowBatteryRule(warn_pct=20.0, clear_pct=25.0)


@pytest.fixture
def ctx():
    return RuleContext()


def test_first_frame_above_threshold_no_alert(rule, ctx):
    alerts = rule.evaluate(make_frame(80.0), ctx)
    assert alerts == []


def test_transition_into_low_fires_alert(rule, ctx):
    ctx.prior_battery_pct = 21.0  # was above threshold
    alerts = rule.evaluate(make_frame(19.0), ctx)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "LOW_BATTERY"
    assert alerts[0].severity == "WARNING"
    assert ctx.low_battery_active is True


def test_already_low_no_repeat_alert(rule, ctx):
    ctx.prior_battery_pct = 21.0
    rule.evaluate(make_frame(19.0), ctx)  # fires, sets low_battery_active
    ctx.prior_battery_pct = 19.0

    alerts = rule.evaluate(make_frame(18.0), ctx)  # stays low
    assert alerts == []


def test_recovery_above_clear_pct_resets_state(rule, ctx):
    ctx.prior_battery_pct = 21.0
    rule.evaluate(make_frame(19.0), ctx)
    ctx.prior_battery_pct = 19.0

    rule.evaluate(make_frame(26.0), ctx)  # recovers above clear_pct=25
    assert ctx.low_battery_active is False


def test_reentry_after_recovery_fires_again(rule, ctx):
    ctx.prior_battery_pct = 21.0
    rule.evaluate(make_frame(19.0), ctx)
    ctx.prior_battery_pct = 19.0

    rule.evaluate(make_frame(26.0), ctx)  # recover
    ctx.prior_battery_pct = 26.0

    alerts = rule.evaluate(make_frame(19.0), ctx)  # drop again
    assert len(alerts) == 1


def test_first_frame_already_below_threshold_fires(rule, ctx):
    # prior_battery_pct is None (first frame ever)
    alerts = rule.evaluate(make_frame(15.0), ctx)
    assert len(alerts) == 1
    assert ctx.low_battery_active is True


def test_exactly_at_threshold_no_alert(rule, ctx):
    ctx.prior_battery_pct = 21.0
    # warn_pct=20.0, battery is exactly 20.0 — NOT below, no alert
    alerts = rule.evaluate(make_frame(20.0), ctx)
    assert alerts == []


def test_hysteresis_does_not_clear_below_clear_pct(rule, ctx):
    ctx.prior_battery_pct = 21.0
    rule.evaluate(make_frame(19.0), ctx)
    ctx.prior_battery_pct = 19.0

    rule.evaluate(make_frame(22.0), ctx)  # above warn but below clear_pct=25
    assert ctx.low_battery_active is True  # not cleared yet
