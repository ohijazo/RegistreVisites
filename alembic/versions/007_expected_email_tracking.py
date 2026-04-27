"""Add email-tracking fields to expected_visits

Revision ID: 007
Revises: 006
Create Date: 2026-04-27

last_email_sent_at i last_email_recipients permeten mostrar al detall
de la visita prevista quan i a qui s'ha enviat l'última notificació
per email (enviament manual des del panell admin).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("last_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "expected_visits",
        sa.Column("last_email_recipients", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expected_visits", "last_email_recipients")
    op.drop_column("expected_visits", "last_email_sent_at")
