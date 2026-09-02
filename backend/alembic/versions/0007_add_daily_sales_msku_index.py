"""Index daily sales by MSKU for the logistics cache lookup."""

from alembic import op


revision = "0007_daily_sales_msku_index"
down_revision = "0006_create_chat_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_daily_sales_msku_date",
        "daily_sales",
        ["amazon_sku", "sales_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_daily_sales_msku_date", table_name="daily_sales")
