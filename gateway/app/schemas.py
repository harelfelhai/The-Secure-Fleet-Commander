"""
Local Pydantic schemas for gateway ↔ backend message contract.
Intentionally duplicated from the backend — the gateway is a separate deployable
and must not import backend code.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TelemetryFrame(BaseModel):
    msg_type: Literal["TELEMETRY"] = "TELEMETRY"
    schema_version: Literal["1.0"] = "1.0"
    agent_id: str
    timestamp: datetime
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float
    battery_pct: Annotated[float, Field(ge=0, le=100)]
    is_backfill: bool = False


class CommandDispatch(BaseModel):
    msg_type: Literal["COMMAND"]
    command_id: str
    command_type: Literal["LAND", "RTH", "CUT_MOTORS"]
    issued_at: datetime


class AckFrame(BaseModel):
    msg_type: Literal["ACK"] = "ACK"
    command_id: str
    status: Literal["ACKNOWLEDGED", "FAILED", "REJECTED"]
    acked_at: datetime


class ReadyMessage(BaseModel):
    msg_type: Literal["READY"]
    agent_id: str
    session_id: str
