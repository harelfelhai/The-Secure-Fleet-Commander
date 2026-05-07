from app.schemas.messages import TelemetryFrame
from app.services.rules_engine import InternalAlert, Rule, RuleContext


class LowBatteryRule(Rule):
    """
    Edge-triggered low-battery alert with hysteresis.

    Fires when battery drops below warn_pct (entry edge).
    Suppressed while battery stays below warn_pct (dedup).
    Clears when battery recovers above clear_pct (hysteresis band prevents oscillation).
    On first frame (prior=None), fires immediately if battery is already below warn_pct.
    """

    name = "low_battery"

    def __init__(self, warn_pct: float = 20.0, clear_pct: float = 25.0) -> None:
        self.warn_pct = warn_pct
        self.clear_pct = clear_pct

    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]:
        current = frame.battery_pct
        prior = ctx.prior_battery_pct

        if not ctx.low_battery_active:
            # Fire on entry: first frame below threshold, or transition from above threshold
            if current < self.warn_pct and (prior is None or prior >= self.warn_pct):
                ctx.low_battery_active = True
                return [
                    InternalAlert(
                        alert_type="LOW_BATTERY",
                        severity="WARNING",
                        message=f"Battery low: {current:.1f}%",
                        context={"battery_pct": current, "threshold_pct": self.warn_pct},
                    )
                ]
        else:
            # Clear hysteresis when battery recovers above clear_pct
            if current >= self.clear_pct:
                ctx.low_battery_active = False

        return []
