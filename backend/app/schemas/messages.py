"""
Pydantic v2 schemas for all WebSocket message types.
These are the runtime validators for the contract defined in shared/schemas/messages.json.
schema_version "1.0" for all MVP messages.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TelemetryFrame(BaseModel):
    """Inbound from Gateway → Backend."""

    msg_type: Literal["TELEMETRY"]
    schema_version: Literal["1.0"]
    agent_id: str
    timestamp: datetime
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float
    battery_pct: Annotated[float, Field(ge=0, le=100)]


class WaypointPayload(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: Annotated[float, Field(ge=0)]


class FrontendCommand(BaseModel):
    """Inbound from Frontend → Backend."""

    msg_type: Literal["COMMAND"]
    command_type: Literal["GO_TO_WAYPOINT"]
    agent_id: str
    payload: WaypointPayload


class CommandDispatch(BaseModel):
    """Outbound from Backend → Gateway."""

    msg_type: Literal["COMMAND"] = "COMMAND"
    command_id: str
    command_type: Literal["GO_TO_WAYPOINT"] = "GO_TO_WAYPOINT"
    payload: WaypointPayload
    issued_at: datetime


class AckFrame(BaseModel):
    """Inbound from Gateway → Backend."""

    msg_type: Literal["ACK"]
    command_id: str
    status: Literal["ACKNOWLEDGED", "FAILED", "REJECTED"]
    acked_at: datetime


class AgentStatus(BaseModel):
    agent_id: str
    display_name: str
    latitude: float
    longitude: float
    altitude_m: float
    battery_pct: float
    last_seen_at: datetime
    status: Literal["ONLINE", "STALE"]


class FleetUpdate(BaseModel):
    """Outbound from Backend → Frontend (fan-out on every telemetry frame)."""

    msg_type: Literal["FLEET_UPDATE"] = "FLEET_UPDATE"
    agents: list[AgentStatus]


class AlertMessage(BaseModel):
    """
    Outbound from Backend → Frontend.
    Replaces the narrower ViolationAlert — covers all rule-triggered events.
    alert_type discriminates the event; context carries type-specific fields.
    """

    msg_type: Literal["ALERT"] = "ALERT"
    alert_type: Literal["GEOFENCE_VIOLATION", "LOW_BATTERY"]
    severity: Literal["WARNING", "CRITICAL"]
    agent_id: str
    message: str
    context: dict[str, Any]
    detected_at: datetime
