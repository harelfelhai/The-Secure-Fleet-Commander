"""
FastAPI dependency factories.

RulesEngine and FleetBroadcaster are application-lifetime singletons.
lru_cache(maxsize=1) on a zero-argument function is the idiomatic way to achieve
this without a global variable — FastAPI calls the function each time but Python
returns the cached instance.
"""

from functools import lru_cache

from app.config import settings
from app.services.broadcaster import FleetBroadcaster
from app.services.connection_manager import frontend_manager
from app.services.rules.geofence import GeofenceRule
from app.services.rules.low_battery import LowBatteryRule
from app.services.rules_engine import RulesEngine


@lru_cache(maxsize=1)
def get_rules_engine() -> RulesEngine:
    return RulesEngine(
        rules=[
            GeofenceRule(),
            LowBatteryRule(
                warn_pct=settings.battery_warn_pct,
                clear_pct=settings.battery_clear_pct,
            ),
        ]
    )


@lru_cache(maxsize=1)
def get_broadcaster() -> FleetBroadcaster:
    return FleetBroadcaster(frontend_manager=frontend_manager)
