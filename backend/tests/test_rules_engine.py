"""
Unit tests for RulesEngine orchestration.
Uses stub rules to verify context passing, prior_battery update, and error isolation.
"""

from app.schemas.messages import TelemetryFrame
from app.services.rules_engine import InternalAlert, Rule, RuleContext, RulesEngine

FRAME = TelemetryFrame.model_validate(
    dict(
        msg_type="TELEMETRY",
        schema_version="1.0",
        agent_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        timestamp="2026-05-01T10:00:00Z",
        latitude=32.0,
        longitude=34.0,
        altitude_m=50.0,
        battery_pct=50.0,
    )
)


class AlwaysAlertRule(Rule):
    name = "always_alert"

    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]:
        return [InternalAlert("TEST", "WARNING", "test alert", {})]


class NeverAlertRule(Rule):
    name = "never_alert"

    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]:
        return []


class ExplodingRule(Rule):
    name = "exploding"

    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]:
        raise RuntimeError("rule exploded")


def test_returns_alerts_from_all_rules():
    engine = RulesEngine(rules=[AlwaysAlertRule(), AlwaysAlertRule()])
    alerts = engine.evaluate(FRAME)
    assert len(alerts) == 2


def test_no_alerts_when_all_rules_silent():
    engine = RulesEngine(rules=[NeverAlertRule()])
    assert engine.evaluate(FRAME) == []


def test_prior_battery_updated_after_evaluate():
    engine = RulesEngine(rules=[NeverAlertRule()])
    engine.evaluate(FRAME)
    ctx = engine.get_context(str(FRAME.agent_id))
    assert ctx.prior_battery_pct == 50.0


def test_exploding_rule_does_not_stop_other_rules():
    engine = RulesEngine(rules=[ExplodingRule(), AlwaysAlertRule()])
    alerts = engine.evaluate(FRAME)
    assert len(alerts) == 1  # AlwaysAlertRule still ran


def test_clear_agent_state_removes_context():
    engine = RulesEngine(rules=[NeverAlertRule()])
    engine.evaluate(FRAME)
    agent_id = str(FRAME.agent_id)
    assert agent_id in engine._contexts
    engine.clear_agent_state(agent_id)
    assert agent_id not in engine._contexts


def test_context_created_fresh_per_agent():
    engine = RulesEngine(rules=[NeverAlertRule()])
    frame_a = TelemetryFrame.model_validate(
        {**FRAME.model_dump(), "agent_id": "aaaaaaaa-0000-0000-0000-000000000000"}
    )
    frame_b = TelemetryFrame.model_validate(
        {**FRAME.model_dump(), "agent_id": "bbbbbbbb-0000-0000-0000-000000000000"}
    )
    engine.evaluate(frame_a)
    engine.evaluate(frame_b)
    assert len(engine._contexts) == 2
