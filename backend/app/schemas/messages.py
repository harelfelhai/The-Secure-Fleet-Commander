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


class FrontendCommand(BaseModel):
    """Inbound from Frontend → Backend. Emergency override commands only — no parameters."""

    msg_type: Literal["COMMAND"]
    command_type: Literal["LAND", "RTH", "CUT_MOTORS"]
    agent_id: str


class CommandDispatch(BaseModel):
    """Outbound from Backend → Gateway. Emergency override commands — no coordinate payload."""

    msg_type: Literal["COMMAND"] = "COMMAND"
    command_id: str
    command_type: Literal["LAND", "RTH", "CUT_MOTORS"]
    issued_at: datetime


class CommandSent(BaseModel):
    """Outbound Backend → Frontend (originating client only). Command accepted and dispatched."""

    msg_type: Literal["COMMAND_SENT"] = "COMMAND_SENT"
    command_id: str
    agent_id: str
    command_type: Literal["LAND", "RTH", "CUT_MOTORS"]
    issued_at: datetime


class CommandError(BaseModel):
    """Outbound Backend → Frontend (originating client only). Command could not be dispatched."""

    msg_type: Literal["COMMAND_ERROR"] = "COMMAND_ERROR"
    agent_id: str | None = None
    reason: str


class AckFrame(BaseModel):
    """Inbound from Gateway → Backend."""

    msg_type: Literal["ACK"]
    command_id: str
    status: Literal["ACKNOWLEDGED", "FAILED", "REJECTED"]
    acked_at: datetime


class LinkStatusMessage(BaseModel):
    """
    Inbound from Gateway → Backend.
    Sent when the gateway detects a change in its radio link to a specific field agent.
    The gateway remains cloud-connected; only the field radio link changed.
    """

    msg_type: Literal["LINK_STATUS"]
    agent_id: str
    link_status: Literal["LINKED", "RADIO_LOST"]
    detected_at: datetime


class AgentStatus(BaseModel):
    agent_id: str
    display_name: str
    latitude: float
    longitude: float
    altitude_m: float
    battery_pct: float
    last_seen_at: datetime
    status: Literal["ONLINE", "STALE"]
    link_status: Literal["LINKED", "RADIO_LOST", "CLOUD_LOST"] = "LINKED"


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
