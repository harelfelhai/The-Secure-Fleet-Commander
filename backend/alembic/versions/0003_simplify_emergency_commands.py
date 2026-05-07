"""simplify command_logs for emergency-only commands

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-03

Scope change: system is now a Safety Monitor with three emergency override commands
(LAND, RTH, CUT_MOTORS) instead of full mission planning (GO_TO_WAYPOINT).

Changes:
  - command_logs.command_type: narrows to String(20), removes GO_TO_WAYPOINT server_default
  - command_logs.payload: adds server_default of '{}' (emergency commands carry no coordinates)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "command_logs",
        "command_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "command_logs",
        "payload",
        existing_nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        "command_logs",
        "payload",
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "command_logs",
        "command_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        server_default="GO_TO_WAYPOINT",
        existing_nullable=False,
    )
