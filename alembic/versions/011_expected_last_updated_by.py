"""Add last_updated_by_id to expected_visits

Revision ID: 011
Revises: 010
Create Date: 2026-04-27

Permet mostrar al detall qui ha estat l'últim que ha modificat una
visita prevista, no només qui l'ha creat.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("last_updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_expected_visits_last_updated_by",
        "expected_visits", "admin_users",
        ["last_updated_by_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_expected_visits_last_updated_by",
        "expected_visits", type_="foreignkey",
    )
    op.drop_column("expected_visits", "last_updated_by_id")
