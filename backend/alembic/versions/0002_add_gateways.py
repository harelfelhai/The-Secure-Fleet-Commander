"""add gateways table and agent link_status

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-03

Adds:
  - gateways table (hardware_id, display_name, registered_at, last_connected_at)
  - agents.gateway_id FK → gateways.id (nullable — agents may predate gateway records)
  - agents.link_status  (LINKED | RADIO_LOST | CLOUD_LOST, default LINKED)
  - idx_agents_gateway  on agents.gateway_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hardware_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hardware_id"),
    )

    op.add_column(
        "agents",
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column(
            "link_status",
            sa.String(length=20),
            nullable=False,
            server_default="LINKED",
        ),
    )
    op.create_foreign_key(
        "fk_agents_gateway_id",
        "agents",
        "gateways",
        ["gateway_id"],
        ["id"],
    )
    op.create_index("idx_agents_gateway", "agents", ["gateway_id"])


def downgrade() -> None:
    op.drop_index("idx_agents_gateway", table_name="agents")
    op.drop_constraint("fk_agents_gateway_id", "agents", type_="foreignkey")
    op.drop_column("agents", "link_status")
    op.drop_column("agents", "gateway_id")
    op.drop_table("gateways")
