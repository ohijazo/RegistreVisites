"""Add id_document_hash for safe DNI lookup

Revision ID: 004
Revises: 003
Create Date: 2026-04-27

Afegeix una columna `id_document_hash` (HMAC-SHA256 del DNI normalitzat amb
pebre) que permet cercar visitants repetits sense desxifrar AES-GCM. Es deixa
nullable per a compatibilitat amb registres existents fins que el script de
backfill els ompli.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "visits",
        sa.Column("id_document_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_visits_id_document_hash",
        "visits",
        ["id_document_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_visits_id_document_hash", table_name="visits")
    op.drop_column("visits", "id_document_hash")
