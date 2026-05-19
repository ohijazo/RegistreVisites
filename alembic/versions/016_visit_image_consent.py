"""Add image_consent column to visits

Revision ID: 016
Revises: 015
Create Date: 2026-05-19

Emmagatzema si el visitant ha autoritzat o no l'ús de la seva imatge/veu
amb finalitats corporatives i de comunicació. La columna és nullable
perquè els registres preexistents (a qui no se'ls va preguntar) quedin
com a NULL i siguin distingibles dels que han respost explícitament 'no'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("image_consent", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "image_consent")
