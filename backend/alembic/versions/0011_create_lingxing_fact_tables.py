"""Add grain-aware LingXing sales, inventory and profit fact tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_lingxing_fact_tables"
down_revision = "0010_merge_lingxing_container"
branch_labels = None
depends_on = None


def _uuid(name: str, *args, **kwargs):
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def _json(name: str, **kwargs):
    return sa.Column(name, postgresql.JSONB(), **kwargs)


def upgrade() -> None:
    op.create_table(
        "lingxing_sales_daily",
        _uuid("id", primary_key=True, nullable=False),
        sa.Column("sales_date", sa.Date(), nullable=False),
        _uuid("msku_product_id", sa.ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")),
        _uuid("listing_id", sa.ForeignKey("lingxing_listings.id", ondelete="SET NULL")),
        _uuid("store_id", sa.ForeignKey("lingxing_stores.id", ondelete="SET NULL")),
        _uuid("market_id", sa.ForeignKey("lingxing_markets.id", ondelete="SET NULL")),
        sa.Column("currency_code", sa.String(length=16)),
        sa.Column("query_grain", sa.String(length=64), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_row_key", sa.String(length=255), nullable=False),
        sa.Column("volume", sa.Numeric(18, 4)),
        sa.Column("sales_amount", sa.Numeric(18, 4)),
        sa.Column("order_items", sa.Numeric(18, 4)),
        sa.Column("refund_quantity", sa.Numeric(18, 4)),
        _json("raw_payload", nullable=False),
        _uuid("sync_batch_id", sa.ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sales_date", "query_fingerprint", "source_row_key", name="uq_lingxing_sales_daily_source_row"),
    )
    op.create_index("ix_lingxing_sales_daily_msku_date", "lingxing_sales_daily", ["msku_product_id", "sales_date"])
    op.create_index("ix_lingxing_sales_daily_market_date", "lingxing_sales_daily", ["market_id", "sales_date"])

    op.create_table(
        "lingxing_inventory_snapshots",
        _uuid("id", primary_key=True, nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("msku_product_id", sa.ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")),
        _uuid("listing_id", sa.ForeignKey("lingxing_listings.id", ondelete="SET NULL")),
        _uuid("store_id", sa.ForeignKey("lingxing_stores.id", ondelete="SET NULL")),
        _uuid("market_id", sa.ForeignKey("lingxing_markets.id", ondelete="SET NULL")),
        sa.Column("warehouse_external_id", sa.String(length=128)),
        sa.Column("inventory_source", sa.String(length=32), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_row_key", sa.String(length=255), nullable=False),
        sa.Column("available_qty", sa.Numeric(18, 4)),
        sa.Column("reserved_qty", sa.Numeric(18, 4)),
        sa.Column("inbound_working_qty", sa.Numeric(18, 4)),
        sa.Column("inbound_shipped_qty", sa.Numeric(18, 4)),
        sa.Column("inbound_receiving_qty", sa.Numeric(18, 4)),
        sa.Column("unsellable_qty", sa.Numeric(18, 4)),
        _json("age_buckets"),
        _json("amounts"),
        _json("raw_payload", nullable=False),
        _uuid("sync_batch_id", sa.ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("snapshot_at", "query_fingerprint", "source_row_key", name="uq_lingxing_inventory_snapshot_source_row"),
    )
    op.create_index("ix_lingxing_inventory_snapshots_msku_time", "lingxing_inventory_snapshots", ["msku_product_id", "snapshot_at"])
    op.create_index("ix_lingxing_inventory_snapshots_source_time", "lingxing_inventory_snapshots", ["inventory_source", "snapshot_at"])

    op.create_table(
        "lingxing_profit_facts",
        _uuid("id", primary_key=True, nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        _uuid("msku_product_id", sa.ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")),
        _uuid("listing_id", sa.ForeignKey("lingxing_listings.id", ondelete="SET NULL")),
        _uuid("store_id", sa.ForeignKey("lingxing_stores.id", ondelete="SET NULL")),
        _uuid("market_id", sa.ForeignKey("lingxing_markets.id", ondelete="SET NULL")),
        sa.Column("currency_code", sa.String(length=16)),
        sa.Column("summary_field", sa.String(length=64), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_row_key", sa.String(length=255), nullable=False),
        sa.Column("volume", sa.Numeric(18, 4)),
        sa.Column("sales_amount", sa.Numeric(18, 4)),
        sa.Column("gross_profit", sa.Numeric(18, 4)),
        sa.Column("net_amount", sa.Numeric(18, 4)),
        sa.Column("total_costs", sa.Numeric(18, 4)),
        sa.Column("ad_cost", sa.Numeric(18, 4)),
        sa.Column("refund_amount", sa.Numeric(18, 4)),
        _json("raw_payload", nullable=False),
        _uuid("sync_batch_id", sa.ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("period_start", "period_end", "query_fingerprint", "source_row_key", name="uq_lingxing_profit_fact_source_row"),
    )
    op.create_index("ix_lingxing_profit_facts_msku_period", "lingxing_profit_facts", ["msku_product_id", "period_start", "period_end"])
    op.create_index("ix_lingxing_profit_facts_currency_period", "lingxing_profit_facts", ["currency_code", "period_start"])


def downgrade() -> None:
    op.drop_index("ix_lingxing_profit_facts_currency_period", table_name="lingxing_profit_facts")
    op.drop_index("ix_lingxing_profit_facts_msku_period", table_name="lingxing_profit_facts")
    op.drop_table("lingxing_profit_facts")
    op.drop_index("ix_lingxing_inventory_snapshots_source_time", table_name="lingxing_inventory_snapshots")
    op.drop_index("ix_lingxing_inventory_snapshots_msku_time", table_name="lingxing_inventory_snapshots")
    op.drop_table("lingxing_inventory_snapshots")
    op.drop_index("ix_lingxing_sales_daily_market_date", table_name="lingxing_sales_daily")
    op.drop_index("ix_lingxing_sales_daily_msku_date", table_name="lingxing_sales_daily")
    op.drop_table("lingxing_sales_daily")
