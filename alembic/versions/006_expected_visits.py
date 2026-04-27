"""Add expected_visits table

Revision ID: 006
Revises: 005
Create Date: 2026-04-27

Visites planificades amb antelació pel personal intern. No es vinculen
automàticament a la taula visits — l'amfitrió és text lliure i
l'estat es gestiona manualment.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expected_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("visitor_name", sa.String(length=250), nullable=False),
        sa.Column("visitor_company", sa.String(length=200), nullable=True),
        sa.Column("visitor_phone", sa.String(length=30), nullable=True),
        sa.Column("host_name", sa.String(length=200), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("expected_date", sa.Date(), nullable=False),
        sa.Column("expected_time", sa.Time(), nullable=True),
        sa.Column("visit_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_expected_visits_expected_date",
                    "expected_visits", ["expected_date"])
    op.create_index("ix_expected_visits_status",
                    "expected_visits", ["status"])


def downgrade() -> None:
    op.drop_index("ix_expected_visits_status", table_name="expected_visits")
    op.drop_index("ix_expected_visits_expected_date", table_name="expected_visits")
    op.drop_table("expected_visits")
