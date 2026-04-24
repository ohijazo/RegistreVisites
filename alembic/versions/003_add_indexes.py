"""Add performance indexes

Revision ID: 003
Revises: 002
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_visits_checked_out_at", "visits", ["checked_out_at"])
    op.create_index("ix_visits_checked_in_at", "visits", ["checked_in_at"])
    op.create_index("ix_visits_exit_token", "visits", ["exit_token"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action")
    op.drop_index("ix_audit_logs_created_at")
    op.drop_index("ix_visits_exit_token")
    op.drop_index("ix_visits_checked_in_at")
    op.drop_index("ix_visits_checked_out_at")
