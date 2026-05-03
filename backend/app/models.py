import uuid
from datetime import datetime

from sqlalchemy import DateTime, Double, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Gateway(Base):
    """A physical gateway device that bridges field agents to the cloud over radio."""

    __tablename__ = "gateways"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hardware_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="gateway")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hardware_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DRONE")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateways.id"), nullable=True
    )
    link_status: Mapped[str] = mapped_column(String(20), nullable=False, default="LINKED")

    gateway: Mapped["Gateway | None"] = relationship(back_populates="agents")
    sessions: Mapped[list["FlightSession"]] = relationship(back_populates="agent")
    breadcrumbs: Mapped[list["GpsBreadcrumb"]] = relationship(back_populates="agent")
    command_logs: Mapped[list["CommandLog"]] = relationship(back_populates="agent")
    violation_logs: Mapped[list["ViolationLog"]] = relationship(back_populates="agent")


class FlightSession(Base):
    __tablename__ = "flight_sessions"
    __table_args__ = (
        Index("idx_sessions_agent_active", "agent_id", postgresql_where="ended_at IS NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="sessions")
    breadcrumbs: Mapped[list["GpsBreadcrumb"]] = relationship(back_populates="session")


class GpsBreadcrumb(Base):
    __tablename__ = "gps_breadcrumbs"
    __table_args__ = (Index("idx_breadcrumbs_agent_time", "agent_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flight_sessions.id"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Double(), nullable=False)
    longitude: Mapped[float] = mapped_column(Double(), nullable=False)
    altitude_m: Mapped[float] = mapped_column(Double(), nullable=False)
    battery_pct: Mapped[float] = mapped_column(Double(), nullable=False)

    session: Mapped["FlightSession"] = relationship(back_populates="breadcrumbs")
    agent: Mapped["Agent"] = relationship(back_populates="breadcrumbs")


class CommandLog(Base):
    __tablename__ = "command_logs"
    __table_args__ = (Index("idx_commands_agent", "agent_id", "issued_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False, default="GO_TO_WAYPOINT")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SENT")
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="command_logs")


class ViolationLog(Base):
    __tablename__ = "violation_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    zone_name: Mapped[str] = mapped_column(Text(), nullable=False)
    latitude: Mapped[float] = mapped_column(Double(), nullable=False)
    longitude: Mapped[float] = mapped_column(Double(), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship(back_populates="violation_logs")
