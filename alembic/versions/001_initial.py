"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("qr_token", sa.String(64), unique=True, nullable=False),
        sa.Column("active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name_ca", sa.String(200), nullable=False),
        sa.Column("name_es", sa.String(200), nullable=False),
        sa.Column("name_fr", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("order", sa.Integer(), default=0),
        sa.Column("active", sa.Boolean(), default=True),
    )

    op.create_table(
        "legal_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_ca", sa.Text(), nullable=False),
        sa.Column("content_es", sa.Text(), nullable=False),
        sa.Column("content_fr", sa.Text(), nullable=False),
        sa.Column("content_en", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id")),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(150), nullable=False),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("id_document_enc", sa.LargeBinary(), nullable=False),
        sa.Column("id_document_iv", sa.LargeBinary(), nullable=False),
        sa.Column("phone", sa.String(30)),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column("visit_reason", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("legal_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_documents.id")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("checked_out_at", sa.DateTime(timezone=True)),
        sa.Column("checkout_method", sa.String(10)),
        sa.Column("exit_token", sa.String(64), unique=True),
        sa.Column("exit_pin", sa.String(6)),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(200), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), default="receptionist"),
        sa.Column("active", sa.Boolean(), default=True),
        sa.Column("last_login", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id")),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("detail", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("admin_users")
    op.drop_table("visits")
    op.drop_table("legal_documents")
    op.drop_table("departments")
    op.drop_table("locations")
