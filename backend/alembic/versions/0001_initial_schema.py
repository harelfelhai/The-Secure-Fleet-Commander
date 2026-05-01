"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-01

Creates: agents, flight_sessions, gps_breadcrumbs, command_logs, violation_logs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hardware_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("device_type", sa.String(length=50), nullable=False, server_default="DRONE"),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hardware_id"),
    )

    op.create_table(
        "flight_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sessions_agent_active",
        "flight_sessions",
        ["agent_id"],
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "gps_breadcrumbs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("altitude_m", sa.Double(), nullable=False),
        sa.Column("battery_pct", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["flight_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_breadcrumbs_agent_time",
        "gps_breadcrumbs",
        ["agent_id", sa.text("recorded_at DESC")],
    )

    op.create_table(
        "command_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "command_type", sa.String(length=50), nullable=False, server_default="GO_TO_WAYPOINT"
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SENT"),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_commands_agent",
        "command_logs",
        ["agent_id", sa.text("issued_at DESC")],
    )

    op.create_table(
        "violation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_name", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("violation_logs")
    op.drop_index("idx_commands_agent", table_name="command_logs")
    op.drop_table("command_logs")
    op.drop_index("idx_breadcrumbs_agent_time", table_name="gps_breadcrumbs")
    op.drop_table("gps_breadcrumbs")
    op.drop_index("idx_sessions_agent_active", table_name="flight_sessions")
    op.drop_table("flight_sessions")
    op.drop_table("agents")
