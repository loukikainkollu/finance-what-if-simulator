"""create core tables

Revision ID: 0001_create_core
Revises: 
Create Date: 2025-09-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enum for report type
    report_type_enum = sa.Enum("pdf", "docx", name="report_type_enum")
    report_type_enum.create(op.get_bind(), checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # scenarios
    op.create_table(
        "scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employees", sa.Integer(), nullable=False),
        sa.Column("salary_per_employee", sa.Integer(), nullable=False),
        sa.Column("marketing_spend", sa.Integer(), nullable=False),
        sa.Column("product_price", sa.Integer(), nullable=False),
        sa.Column("forecast_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # reports
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_type", report_type_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # usage
    op.create_table(
        "usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("scenarios_run", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reports_exported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_usage_user_id"),
    )


def downgrade() -> None:
    op.drop_table("usage")
    op.drop_table("reports")
    op.drop_table("scenarios")
    op.drop_table("users")

    # Drop enum type
    sa.Enum(name="report_type_enum").drop(op.get_bind(), checkfirst=True)