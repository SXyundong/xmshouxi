"""Add stable read-only views for Agent analysis."""

from alembic import op


revision = "0012_lingxing_analysis_views"
down_revision = "0011_lingxing_fact_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW lingxing_sales_analysis AS
        SELECT DISTINCT ON (f.sales_date, f.source_row_key)
            f.id,
            f.sales_date,
            f.query_grain,
            COALESCE(p.msku, f.raw_payload->>'msku', f.raw_payload->>'seller_sku') AS msku,
            COALESCE(f.raw_payload->>'asin', f.raw_payload->>'amazon_asin') AS asin,
            f.msku_product_id,
            f.listing_id,
            f.store_id,
            f.market_id,
            f.currency_code,
            f.volume,
            f.sales_amount,
            f.order_items,
            f.refund_quantity,
            f.raw_payload,
            f.fetched_at
        FROM lingxing_sales_daily f
        LEFT JOIN lingxing_msku_products p ON p.id = f.msku_product_id
        ORDER BY f.sales_date, f.source_row_key, f.fetched_at DESC;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW lingxing_profit_analysis AS
        SELECT DISTINCT ON (f.period_start, f.period_end, f.source_row_key)
            f.id,
            f.period_start,
            f.period_end,
            f.summary_field,
            COALESCE(p.msku, f.raw_payload->>'msku', f.raw_payload->>'seller_sku') AS msku,
            COALESCE(f.raw_payload->>'asin', f.raw_payload->>'asin_list') AS asin,
            f.msku_product_id,
            f.listing_id,
            f.store_id,
            f.market_id,
            f.currency_code,
            f.volume,
            f.sales_amount,
            f.gross_profit,
            f.net_amount,
            f.total_costs,
            f.ad_cost,
            f.refund_amount,
            f.raw_payload,
            f.fetched_at
        FROM lingxing_profit_facts f
        LEFT JOIN lingxing_msku_products p ON p.id = f.msku_product_id
        ORDER BY f.period_start, f.period_end, f.source_row_key, f.fetched_at DESC;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW lingxing_inventory_latest AS
        SELECT DISTINCT ON (f.source_row_key)
            f.id,
            f.snapshot_at,
            COALESCE(p.msku, f.raw_payload->>'seller_sku') AS msku,
            f.raw_payload->>'asin' AS asin,
            f.raw_payload->>'fnsku' AS fnsku,
            f.msku_product_id,
            f.listing_id,
            f.store_id,
            f.market_id,
            f.warehouse_external_id,
            f.inventory_source,
            f.available_qty,
            f.reserved_qty,
            f.inbound_working_qty,
            f.inbound_shipped_qty,
            f.inbound_receiving_qty,
            f.unsellable_qty,
            f.age_buckets,
            f.amounts,
            f.raw_payload,
            f.fetched_at
        FROM lingxing_inventory_snapshots f
        LEFT JOIN lingxing_msku_products p ON p.id = f.msku_product_id
        ORDER BY f.source_row_key, f.snapshot_at DESC;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS lingxing_inventory_latest")
    op.execute("DROP VIEW IF EXISTS lingxing_profit_analysis")
    op.execute("DROP VIEW IF EXISTS lingxing_sales_analysis")
