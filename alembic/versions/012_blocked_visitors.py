"""Add blocked_visitors table (watchlist)

Revision ID: 012
Revises: 011
Create Date: 2026-04-28

Llista de DNIs bloquejats: ex-empleats acomiadats, persones amb ordre
d'allunyament, visitants conflictius. Si el hash del DNI introduït al
quiosc coincideix amb un bloqueig actiu, es rebutja el registre amb
un missatge genèric.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blocked_visitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_document_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("blocked_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("internal_label", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_blocked_visitors_hash", "blocked_visitors", ["id_document_hash"])
    op.create_index("ix_blocked_visitors_active", "blocked_visitors", ["active"])


def downgrade() -> None:
    op.drop_index("ix_blocked_visitors_active", table_name="blocked_visitors")
    op.drop_index("ix_blocked_visitors_hash", table_name="blocked_visitors")
    op.drop_table("blocked_visitors")
