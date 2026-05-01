"""
FleetBroadcaster — maintains in-memory agent state and fans out WS messages to all
connected Frontend clients.

Lifecycle:
- update_agent(): called on every successful ingest; updates in-memory state and status.
- mark_stale(): called on Gateway disconnect so frontends see STALE immediately.
- broadcast_fleet_update(): serialises current state → FLEET_UPDATE → all frontends.
- broadcast_alert(): serialises an InternalAlert → ALERT → all frontends.
"""

import logging
from datetime import UTC, datetime

from app.schemas.messages import AgentStatus, AlertMessage, FleetUpdate
from app.services.connection_manager import FrontendConnectionManager
from app.services.rules_engine import InternalAlert

logger = logging.getLogger(__name__)


class FleetBroadcaster:
    def __init__(self, frontend_manager: FrontendConnectionManager) -> None:
        self._frontend = frontend_manager
        self._fleet: dict[str, AgentStatus] = {}

    def update_agent(self, agent_id: str, display_name: str, frame_data: dict) -> None:
        """Update in-memory state for one agent. Called after every persisted frame."""
        self._fleet[agent_id] = AgentStatus(
            agent_id=agent_id,
            display_name=display_name,
            latitude=frame_data["latitude"],
            longitude=frame_data["longitude"],
            altitude_m=frame_data["altitude_m"],
            battery_pct=frame_data["battery_pct"],
            last_seen_at=frame_data["last_seen_at"],
            status="ONLINE",
        )

    def mark_stale(self, agent_id: str) -> None:
        """Mark an agent STALE on disconnect so the next FLEET_UPDATE reflects it."""
        if agent_id in self._fleet:
            current = self._fleet[agent_id]
            self._fleet[agent_id] = AgentStatus(
                agent_id=current.agent_id,
                display_name=current.display_name,
                latitude=current.latitude,
                longitude=current.longitude,
                altitude_m=current.altitude_m,
                battery_pct=current.battery_pct,
                last_seen_at=current.last_seen_at,
                status="STALE",
            )

    async def broadcast_fleet_update(self) -> None:
        if not self._fleet:
            return
        msg = FleetUpdate(agents=list(self._fleet.values()))
        await self._frontend.broadcast(msg.model_dump_json())

    async def broadcast_alert(self, alert: InternalAlert, agent_id: str) -> None:
        msg = AlertMessage(
            alert_type=alert.alert_type,  # type: ignore[arg-type]
            severity=alert.severity,  # type: ignore[arg-type]
            agent_id=agent_id,
            message=alert.message,
            context=alert.context,
            detected_at=datetime.now(UTC),
        )
        await self._frontend.broadcast(msg.model_dump_json())
