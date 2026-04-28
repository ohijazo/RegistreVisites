"""Add visitor_email + visitor_invitation_sent_at to expected_visits

Revision ID: 014
Revises: 013
Create Date: 2026-04-28

Permet enviar al visitant una invitació amb el codi i el QR de
fast-track per email. Ho fa l'usuari manualment des del detall.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("visitor_email", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "expected_visits",
        sa.Column("visitor_invitation_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expected_visits", "visitor_invitation_sent_at")
    op.drop_column("expected_visits", "visitor_email")
