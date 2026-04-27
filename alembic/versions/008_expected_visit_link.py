"""Add visit_id link from expected_visits to visits

Revision ID: 008
Revises: 007
Create Date: 2026-04-27

Vincle directe entre la visita prevista i el registre real de quiosc.
S'omple automàticament al flux d'arribada quan nom i empresa coincideixen.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_expected_visits_visit_id",
        "expected_visits", "visits",
        ["visit_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_expected_visits_visit_id",
        "expected_visits", ["visit_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_expected_visits_visit_id", table_name="expected_visits")
    op.drop_constraint("fk_expected_visits_visit_id", "expected_visits", type_="foreignkey")
    op.drop_column("expected_visits", "visit_id")
