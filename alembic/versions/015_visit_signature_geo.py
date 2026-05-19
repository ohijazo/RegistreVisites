"""Add signature geolocation columns to visits

Revision ID: 015
Revises: 014
Create Date: 2026-05-08

Registra la ubicació GPS reportada pel navegador del visitant en el moment
de signar el consentiment legal. Tots els camps són opcionals: si el
visitant denega el permís o el dispositiu no té GPS, queden nuls.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("signature_lat", sa.Float(), nullable=True))
    op.add_column("visits", sa.Column("signature_lon", sa.Float(), nullable=True))
    op.add_column("visits", sa.Column("signature_accuracy_m", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "signature_accuracy_m")
    op.drop_column("visits", "signature_lon")
    op.drop_column("visits", "signature_lat")
