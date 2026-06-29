"""Multi-day expected visits via series_id (shared access_code)

Revision ID: 018
Revises: 017
Create Date: 2026-06-29

Permet agrupar N previsites (una per dia) en una "sèrie" perquè un
visitant que ve varis dies pugui rebre un sol codi d'accés. Cada fila
de la sèrie comparteix `series_id` (UUID) i `access_code`.

Canvis d'índexs sobre `access_code`:
  - Es treu el UNIQUE perquè dins d'una sèrie hi ha N files amb el
    mateix codi.
  - Es manté un índex no únic per a lookups ràpids.
  - Es garanteix unicitat per dia amb un UNIQUE compost
    (access_code, expected_date) — un mateix codi no es pot repetir el
    mateix dia (no té sentit ni a nivell de domini).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expected_visits",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_expected_visits_series_id",
        "expected_visits",
        ["series_id"],
    )

    # Substituir el UNIQUE per un índex normal i moure la unicitat al
    # compost (access_code, expected_date).
    op.drop_index("ix_expected_visits_access_code", table_name="expected_visits")
    op.create_index(
        "ix_expected_visits_access_code",
        "expected_visits",
        ["access_code"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_expected_code_date",
        "expected_visits",
        ["access_code", "expected_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_expected_code_date", "expected_visits", type_="unique"
    )
    op.drop_index("ix_expected_visits_access_code", table_name="expected_visits")
    op.create_index(
        "ix_expected_visits_access_code",
        "expected_visits",
        ["access_code"],
        unique=True,
    )
    op.drop_index("ix_expected_visits_series_id", table_name="expected_visits")
    op.drop_column("expected_visits", "series_id")
