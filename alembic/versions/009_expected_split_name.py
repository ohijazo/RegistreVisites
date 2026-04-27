"""Split expected_visits.visitor_name into first_name + last_name

Revision ID: 009
Revises: 008
Create Date: 2026-04-27

Coherent amb el formulari de visitants al quiosc, on nom i cognoms són
camps separats. La migració divideix els valors existents pel primer
espai (la resta passa a cognoms).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columnes noves nullable per al backfill
    op.add_column(
        "expected_visits",
        sa.Column("visitor_first_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "expected_visits",
        sa.Column("visitor_last_name", sa.String(length=150), nullable=True),
    )

    # Backfill: tot abans del primer espai → first_name; la resta → last_name.
    op.execute(
        """
        UPDATE expected_visits
        SET
            visitor_first_name = SPLIT_PART(visitor_name, ' ', 1),
            visitor_last_name = CASE
                WHEN POSITION(' ' IN visitor_name) > 0
                THEN TRIM(SUBSTRING(visitor_name FROM POSITION(' ' IN visitor_name) + 1))
                ELSE NULL
            END
        WHERE visitor_name IS NOT NULL
        """
    )

    # first_name passa a obligatori; last_name queda opcional
    op.alter_column("expected_visits", "visitor_first_name", nullable=False)

    # Eliminem la columna antiga
    op.drop_column("expected_visits", "visitor_name")


def downgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("visitor_name", sa.String(length=250), nullable=True),
    )
    op.execute(
        """
        UPDATE expected_visits
        SET visitor_name = TRIM(
            visitor_first_name || COALESCE(' ' || visitor_last_name, '')
        )
        """
    )
    op.alter_column("expected_visits", "visitor_name", nullable=False)
    op.drop_column("expected_visits", "visitor_last_name")
    op.drop_column("expected_visits", "visitor_first_name")
