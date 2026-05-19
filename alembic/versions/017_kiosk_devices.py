"""Add kiosk_devices table

Revision ID: 017
Revises: 016
Create Date: 2026-05-19

Dispositius (tablets, ordinadors) matriculats com a quioscs. Substitueix
la restricció per IP en escenaris on els dispositius es connecten per
WiFi i no tenen IP estable. El client guarda una cookie signada amb un
token; al servidor s'emmagatzema només el SHA-256 d'aquest token (com
una contrasenya).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kiosk_devices",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enrolled_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_ip", sa.dialects.postgresql.INET(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_kiosk_devices_token_hash", "kiosk_devices", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_kiosk_devices_token_hash", table_name="kiosk_devices")
    op.drop_table("kiosk_devices")
