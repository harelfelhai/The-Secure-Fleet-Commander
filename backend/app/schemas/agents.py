import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hardware_id: str
    display_name: str
    device_type: str
    registered_at: datetime
    last_seen_at: datetime | None


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int


class BreadcrumbResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recorded_at: datetime
    latitude: float
    longitude: float
    altitude_m: float
    battery_pct: float


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None


class CommandLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_type: str
    status: str
    issued_at: datetime
    acked_at: datetime | None
