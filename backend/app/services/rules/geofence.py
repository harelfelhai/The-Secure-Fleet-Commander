from app.schemas.messages import TelemetryFrame
from app.services import zone_evaluator
from app.services.rules_engine import InternalAlert, Rule, RuleContext


class GeofenceRule(Rule):
    """
    Edge-triggered no-fly zone check.
    Fires ONCE when an agent enters a zone; suppresses while inside (dedup via ctx.active_zones).
    Clears state when the agent leaves all zones.
    """

    name = "geofence"

    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]:
        violated, zone_name = zone_evaluator.evaluate(frame.longitude, frame.latitude)

        if violated and zone_name is not None:
            if zone_name not in ctx.active_zones:
                ctx.active_zones.add(zone_name)
                return [
                    InternalAlert(
                        alert_type="GEOFENCE_VIOLATION",
                        severity="CRITICAL",
                        message=f"Agent entered restricted zone: {zone_name}",
                        context={"zone_name": zone_name},
                    )
                ]
            # Already inside this zone — suppressed
            return []

        # Agent is not in any zone; clear all active zone state
        ctx.active_zones.clear()
        return []
