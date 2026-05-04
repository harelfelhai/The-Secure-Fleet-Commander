"""
FleetBroadcaster — maintains in-memory agent state and fans out WS messages to all
connected Frontend clients.

Lifecycle:
- update_agent(): called on every successful ingest; updates in-memory state and status.
- mark_cloud_lost(): called on Gateway WS disconnect; marks all agents of that gateway.
- mark_link_status(): called on LINK_STATUS message; updates one agent's radio link state.
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
        # gateway hardware_id → set of agent_ids reporting through it
        self._gateway_agents: dict[str, set[str]] = {}

    def update_agent(
        self,
        agent_id: str,
        display_name: str,
        frame_data: dict,
        gateway_hardware_id: str | None = None,
    ) -> None:
        """Update in-memory state for one agent. Called after every live telemetry frame."""
        current = self._fleet.get(agent_id)
        if current is not None and frame_data["last_seen_at"] <= current.last_seen_at:
            # Stale frame (e.g. arrived out-of-order) — do not overwrite live state
            return
        self._fleet[agent_id] = AgentStatus(
            agent_id=agent_id,
            display_name=display_name,
            latitude=frame_data["latitude"],
            longitude=frame_data["longitude"],
            altitude_m=frame_data["altitude_m"],
            battery_pct=frame_data["battery_pct"],
            last_seen_at=frame_data["last_seen_at"],
            status="ONLINE",
            link_status="LINKED",
        )
        if gateway_hardware_id is not None:
            self._gateway_agents.setdefault(gateway_hardware_id, set()).add(agent_id)

    def mark_cloud_lost(self, gateway_hardware_id: str) -> None:
        """
        Mark all agents that reported through this gateway as CLOUD_LOST.
        Called when the gateway's WebSocket to the backend drops.
        """
        for agent_id in self._gateway_agents.get(gateway_hardware_id, set()):
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
                    link_status="CLOUD_LOST",
                )
        self._gateway_agents.pop(gateway_hardware_id, None)

    def mark_link_status(self, agent_id: str, link_status: str) -> None:
        """
        Update the radio link status for a single agent.
        Called when a gateway sends a LINK_STATUS message (RADIO_LOST / LINKED).
        The gateway WS is still up; only the field radio changed.
        """
        if agent_id not in self._fleet:
            logger.warning("mark_link_status: unknown agent_id %s", agent_id)
            return
        current = self._fleet[agent_id]
        new_status = "STALE" if link_status == "RADIO_LOST" else "ONLINE"
        self._fleet[agent_id] = AgentStatus(
            agent_id=current.agent_id,
            display_name=current.display_name,
            latitude=current.latitude,
            longitude=current.longitude,
            altitude_m=current.altitude_m,
            battery_pct=current.battery_pct,
            last_seen_at=current.last_seen_at,
            status=new_status,
            link_status=link_status,  # type: ignore[arg-type]
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
