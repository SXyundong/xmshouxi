"""Persist container-loading inputs and results for audit/debugging."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_container_loading_runs"
down_revision = "0007_daily_sales_msku_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "container_loading_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_open_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("container_payload", postgresql.JSONB(), nullable=False),
        sa.Column("items_payload", postgresql.JSONB(), nullable=False),
        sa.Column("results_payload", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_container_loading_runs_owner_created",
        "container_loading_runs",
        ["owner_open_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_container_loading_runs_owner_created", table_name="container_loading_runs")
    op.drop_table("container_loading_runs")
