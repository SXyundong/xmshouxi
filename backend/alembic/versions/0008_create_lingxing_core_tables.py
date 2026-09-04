"""Create the LingXing raw, core Listing, and current-state tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_lingxing_core_tables"
down_revision = "0007_daily_sales_msku_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lingxing_sync_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("catalog_version", sa.String(length=128)),
        sa.Column("schema_version", sa.String(length=128)),
        sa.Column("request_params", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("page_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trace_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lingxing_sync_batches_tool_started",
        "lingxing_sync_batches",
        ["tool_id", "started_at"],
    )
    op.create_index("ix_lingxing_sync_batches_status", "lingxing_sync_batches", ["status"])

    op.create_table(
        "lingxing_raw_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sync_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("source_record_key", sa.String(length=255)),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sync_batch_id"], ["lingxing_sync_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lingxing_raw_records_tool_key",
        "lingxing_raw_records",
        ["tool_id", "source_record_key"],
    )
    op.create_index("ix_lingxing_raw_records_batch", "lingxing_raw_records", ["sync_batch_id"])

    op.create_table(
        "lingxing_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sid", sa.BigInteger(), nullable=False),
        sa.Column("seller_id", sa.String(length=128)),
        sa.Column("store_name", sa.String(length=255), nullable=False),
        sa.Column("country_code", sa.String(length=8)),
        sa.Column("platform_code", sa.Integer()),
        sa.Column("currency", sa.String(length=16)),
        sa.Column("status", sa.String(length=32)),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sid", name="uq_lingxing_stores_sid"),
    )

    op.create_table(
        "lingxing_markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("mid", sa.BigInteger(), nullable=False),
        sa.Column("marketplace_id", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=8)),
        sa.Column("marketplace_name", sa.String(length=64)),
        sa.Column("site_url", sa.Text()),
        sa.Column("currency", sa.String(length=16)),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marketplace_id", "mid", name="uq_lingxing_markets_marketplace_mid"),
    )

    op.create_table(
        "lingxing_msku_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("msku", sa.String(length=100), nullable=False),
        sa.Column("lingxing_product_id", sa.BigInteger()),
        sa.Column("local_sku", sa.String(length=100)),
        sa.Column("local_name", sa.Text()),
        sa.Column("brand", sa.String(length=255)),
        sa.Column("principal_uid", sa.BigInteger()),
        sa.Column("principal_name", sa.String(length=255)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("msku", name="uq_lingxing_msku_products_msku"),
    )
    op.create_index("ix_lingxing_msku_products_local_sku", "lingxing_msku_products", ["local_sku"])
    op.create_index(
        "ix_lingxing_msku_products_source_product",
        "lingxing_msku_products",
        ["lingxing_product_id"],
    )

    op.create_table(
        "lingxing_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("lingxing_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("msku_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_market_parameter_id", postgresql.UUID(as_uuid=True)),
        sa.Column("store_id", postgresql.UUID(as_uuid=True)),
        sa.Column("market_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_store_id", sa.BigInteger(), nullable=False),
        sa.Column("source_marketplace_id", sa.String(length=64), nullable=False),
        sa.Column("asin", sa.String(length=32), nullable=False),
        sa.Column("parent_asin", sa.String(length=32)),
        sa.Column("fnsku", sa.String(length=64)),
        sa.Column("local_sku", sa.String(length=100)),
        sa.Column("fulfillment_channel_type", sa.String(length=16)),
        sa.Column("status", sa.Integer()),
        sa.Column("status_text", sa.String(length=32)),
        sa.Column("item_name", sa.Text()),
        sa.Column("variant_text", postgresql.JSONB()),
        sa.Column("seller_category", postgresql.JSONB()),
        sa.Column("first_order_time", sa.String(length=64)),
        sa.Column("open_date_time", sa.String(length=64)),
        sa.Column("on_sale_time", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.ForeignKeyConstraint(
            ["msku_product_id"], ["lingxing_msku_products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_market_parameter_id"],
            ["product_market_parameters.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["lingxing_stores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["market_id"], ["lingxing_markets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lingxing_listing_id", name="uq_lingxing_listings_source_id"),
        sa.UniqueConstraint(
            "msku_product_id",
            "source_store_id",
            "source_marketplace_id",
            "asin",
            name="uq_lingxing_listings_business_identity",
        ),
    )
    op.create_index("ix_lingxing_listings_msku", "lingxing_listings", ["msku_product_id"])
    op.create_index(
        "ix_lingxing_listings_store_market",
        "lingxing_listings",
        ["store_id", "market_id"],
    )
    op.create_index("ix_lingxing_listings_asin", "lingxing_listings", ["asin"])
    op.create_index(
        "ix_lingxing_listings_product_market_parameter",
        "lingxing_listings",
        ["product_market_parameter_id"],
    )

    op.create_table(
        "lingxing_listing_current",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_code", sa.String(length=16)),
        sa.Column("listing_price", sa.Numeric(18, 4)),
        sa.Column("regular_price", sa.Numeric(18, 4)),
        sa.Column("landed_price", sa.Numeric(18, 4)),
        sa.Column("fba_fee", sa.Numeric(18, 4)),
        sa.Column("referral_fee", sa.Numeric(18, 4)),
        sa.Column("afn_fulfillable_quantity", sa.Numeric(18, 4)),
        sa.Column("afn_reserved_quantity", sa.Numeric(18, 4)),
        sa.Column("afn_unsellable_quantity", sa.Numeric(18, 4)),
        sa.Column("afn_inbound_working_quantity", sa.Numeric(18, 4)),
        sa.Column("afn_inbound_shipped_quantity", sa.Numeric(18, 4)),
        sa.Column("afn_inbound_receiving_quantity", sa.Numeric(18, 4)),
        sa.Column("fbm_quantity", sa.Numeric(18, 4)),
        sa.Column("seller_rank", sa.Integer()),
        sa.Column("stars", sa.Numeric(4, 2)),
        sa.Column("reviews_num", sa.BigInteger()),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["lingxing_listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("listing_id"),
    )

    op.create_table(
        "lingxing_listing_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("selected_metrics", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["lingxing_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_batch_id"], ["lingxing_sync_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "sync_batch_id", name="uq_lingxing_listing_snapshot_batch"),
    )
    op.create_index(
        "ix_lingxing_listing_snapshots_listing_time",
        "lingxing_listing_snapshots",
        ["listing_id", "snapshot_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lingxing_listing_snapshots_listing_time", table_name="lingxing_listing_snapshots")
    op.drop_table("lingxing_listing_snapshots")
    op.drop_table("lingxing_listing_current")
    op.drop_index("ix_lingxing_listings_product_market_parameter", table_name="lingxing_listings")
    op.drop_index("ix_lingxing_listings_asin", table_name="lingxing_listings")
    op.drop_index("ix_lingxing_listings_store_market", table_name="lingxing_listings")
    op.drop_index("ix_lingxing_listings_msku", table_name="lingxing_listings")
    op.drop_table("lingxing_listings")
    op.drop_index("ix_lingxing_msku_products_source_product", table_name="lingxing_msku_products")
    op.drop_index("ix_lingxing_msku_products_local_sku", table_name="lingxing_msku_products")
    op.drop_table("lingxing_msku_products")
    op.drop_table("lingxing_markets")
    op.drop_table("lingxing_stores")
    op.drop_index("ix_lingxing_raw_records_batch", table_name="lingxing_raw_records")
    op.drop_index("ix_lingxing_raw_records_tool_key", table_name="lingxing_raw_records")
    op.drop_table("lingxing_raw_records")
    op.drop_index("ix_lingxing_sync_batches_status", table_name="lingxing_sync_batches")
    op.drop_index("ix_lingxing_sync_batches_tool_started", table_name="lingxing_sync_batches")
    op.drop_table("lingxing_sync_batches")
