"""
Rules Engine — evaluates all configured rules against every inbound telemetry frame.

Design:
- Rule is a pure ABC; each rule is stateless in its logic but mutates RuleContext.
- RuleContext holds per-agent state (dedup / hysteresis) and is owned by RulesEngine.
- RulesEngine.evaluate() runs all rules, updates prior_battery_pct, and returns alerts.
- On rule error, the exception is logged and evaluation continues (fail-open for safety).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.schemas.messages import TelemetryFrame

logger = logging.getLogger(__name__)


@dataclass
class InternalAlert:
    alert_type: str  # "GEOFENCE_VIOLATION" | "LOW_BATTERY"
    severity: str  # "WARNING" | "CRITICAL"
    message: str
    context: dict


@dataclass
class RuleContext:
    """
    Mutable per-agent state shared across all rules during a single evaluate() call.
    prior_battery_pct is updated by RulesEngine AFTER all rules run.
    """

    prior_battery_pct: float | None = None
    active_zones: set[str] = field(default_factory=set)
    low_battery_active: bool = False


class Rule(ABC):
    name: str

    @abstractmethod
    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]: ...


class RulesEngine:
    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules
        self._contexts: dict[str, RuleContext] = {}

    def get_context(self, agent_id: str) -> RuleContext:
        if agent_id not in self._contexts:
            self._contexts[agent_id] = RuleContext()
        return self._contexts[agent_id]

    def evaluate(self, frame: TelemetryFrame) -> list[InternalAlert]:
        agent_id = str(frame.agent_id)
        ctx = self.get_context(agent_id)
        alerts: list[InternalAlert] = []

        for rule in self._rules:
            try:
                alerts.extend(rule.evaluate(frame, ctx))
            except Exception:
                logger.error(
                    "Rule %s raised on frame from agent %s",
                    rule.name,
                    agent_id,
                    exc_info=True,
                )

        # Update prior state after all rules have seen the current frame
        ctx.prior_battery_pct = frame.battery_pct
        return alerts

    def clear_agent_state(self, agent_id: str) -> None:
        """Remove per-agent state on disconnect (avoids stale dedup after reconnect)."""
        self._contexts.pop(agent_id, None)
