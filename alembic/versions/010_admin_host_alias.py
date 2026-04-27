"""Add host_alias to admin_users for "Les meves visites previstes" filter

Revision ID: 010
Revises: 009
Create Date: 2026-04-27

Cada admin pot configurar un "host_alias" (text lliure curt: el seu nom
o iniciallat com normalment apareix al camp host_name de les visites
previstes). El llistat i el bàner del dashboard usen aquest valor per
filtrar "Les meves" amb un ILIKE difús.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("host_alias", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "host_alias")
