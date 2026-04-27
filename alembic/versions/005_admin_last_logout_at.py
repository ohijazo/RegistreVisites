"""Add last_logout_at to admin_users for JWT invalidation

Revision ID: 005
Revises: 004
Create Date: 2026-04-27

Permet revocar JWTs emesos abans d'una desconnexió: get_current_admin
rebutja qualsevol token amb iat anterior a last_logout_at.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("last_logout_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "last_logout_at")
