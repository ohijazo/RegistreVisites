"""Add access_code to expected_visits for fast-track at kiosk

Revision ID: 013
Revises: 012
Create Date: 2026-04-28

Codi curt (8 caràcters) que identifica una visita prevista. Es lliura
al visitant per email manual / WhatsApp / QR i li permet saltar-se
l'omplertament del formulari quan arriba al quiosc.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("access_code", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_expected_visits_access_code",
        "expected_visits", ["access_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_expected_visits_access_code", table_name="expected_visits")
    op.drop_column("expected_visits", "access_code")
