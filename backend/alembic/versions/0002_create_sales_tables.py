"""Move logistics sales cache tables into PostgreSQL."""

from alembic import op
import sqlalchemy as sa

revision = "0002_sales_tables"
down_revision = "0001_product_market_parameters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_sales",
        sa.Column("sales_date", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("amazon_sku", sa.String(100), nullable=False, server_default=""),
        sa.Column("product_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(255), nullable=False, server_default=""),
        sa.Column("store", sa.String(255), nullable=False, server_default=""),
        sa.Column("country", sa.String(64), nullable=False, server_default=""),
        sa.Column("platform", sa.String(64), nullable=False, server_default=""),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("sales_date", "sku", "amazon_sku", "country", "store"),
    )
    op.create_index("idx_daily_sales_sku_date", "daily_sales", ["sku", "sales_date"])
    op.create_table(
        "sales_coverage",
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("sales_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("sku", "sales_date"),
    )
    op.create_table(
        "mcp_raw_responses",
        sa.Column("response_id", sa.String(64), primary_key=True),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "sync_jobs",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sync_jobs")
    op.drop_table("mcp_raw_responses")
    op.drop_table("sales_coverage")
    op.drop_index("idx_daily_sales_sku_date", table_name="daily_sales")
    op.drop_table("daily_sales")
