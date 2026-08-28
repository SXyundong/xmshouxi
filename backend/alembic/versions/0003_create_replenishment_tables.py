"""Create replenishment policies, settings, inventory snapshots, and calculation view."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_replenishment"
down_revision = "0002_sales_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replenishment_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("policy_code", sa.String(64), nullable=False),
        sa.Column("policy_name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(8)),
        sa.Column("store", sa.String(255)),
        sa.Column("channel_type", sa.String(32)),
        sa.Column("west_coast_ocean_days", sa.Integer(), nullable=False),
        sa.Column("east_coast_ocean_days", sa.Integer(), nullable=False),
        sa.Column("listing_days", sa.Integer(), nullable=False),
        sa.Column("fbm_to_fba_transfer_days", sa.Integer(), nullable=False),
        sa.Column("overall_buffer_days", sa.Integer(), nullable=False),
        sa.Column("inventory_warning_ratio", sa.Numeric(8, 4), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("west_coast_ocean_days >= 0", name="ck_replenishment_policy_west_days"),
        sa.CheckConstraint("east_coast_ocean_days >= 0", name="ck_replenishment_policy_east_days"),
        sa.CheckConstraint("listing_days >= 0", name="ck_replenishment_policy_listing_days"),
        sa.CheckConstraint("fbm_to_fba_transfer_days >= 0", name="ck_replenishment_policy_fbm_days"),
        sa.CheckConstraint("overall_buffer_days >= 0", name="ck_replenishment_policy_buffer_days"),
        sa.CheckConstraint("inventory_warning_ratio >= 1", name="ck_replenishment_policy_warning_ratio"),
        sa.ForeignKeyConstraint(["country_code"], ["market_codes.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_code"),
    )
    op.execute(
        """
        INSERT INTO replenishment_policies (
            policy_code,
            policy_name,
            west_coast_ocean_days,
            east_coast_ocean_days,
            listing_days,
            fbm_to_fba_transfer_days,
            overall_buffer_days,
            inventory_warning_ratio,
            effective_from
        ) VALUES (
            'DEFAULT',
            '默认备货策略',
            35,
            45,
            10,
            45,
            60,
            1.5,
            CURRENT_DATE
        )
        """
    )

    op.create_table(
        "replenishment_item_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_market_parameter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_date", sa.Date()),
        sa.Column("lifecycle_status", sa.String(64)),
        sa.Column("forecast_daily_sales_override", sa.Numeric(18, 4)),
        sa.Column("warehouse_split_ratio", sa.Numeric(8, 6)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "forecast_daily_sales_override IS NULL OR forecast_daily_sales_override >= 0",
            name="ck_replenishment_setting_forecast",
        ),
        sa.CheckConstraint(
            "warehouse_split_ratio IS NULL OR (warehouse_split_ratio >= 0 AND warehouse_split_ratio <= 1)",
            name="ck_replenishment_setting_split_ratio",
        ),
        sa.ForeignKeyConstraint(
            ["product_market_parameter_id"],
            ["product_market_parameters.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["policy_id"], ["replenishment_policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_market_parameter_id"),
    )

    op.create_table(
        "inventory_position_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_market_parameter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("on_hand_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("in_transit_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("supplier_reserved_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("west_warehouse_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("east_warehouse_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("source", sa.String(64)),
        sa.Column("source_batch_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_market_parameter_id"],
            ["product_market_parameters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_market_parameter_id",
            "snapshot_at",
            name="uq_inventory_position_product_snapshot",
        ),
    )
    op.create_index(
        "ix_inventory_position_product_snapshot",
        "inventory_position_snapshots",
        ["product_market_parameter_id", "snapshot_at"],
    )

    op.execute(
        """
        CREATE VIEW replenishment_recommendations AS
        WITH sales AS (
            SELECT
                sku,
                amazon_sku,
                country,
                COALESCE(SUM(volume) FILTER (
                    WHERE sales_date BETWEEN CURRENT_DATE - 3 AND CURRENT_DATE - 1
                ), 0)::numeric AS sales_3d,
                COALESCE(SUM(volume) FILTER (
                    WHERE sales_date BETWEEN CURRENT_DATE - 7 AND CURRENT_DATE - 1
                ), 0)::numeric AS sales_7d,
                COALESCE(SUM(volume) FILTER (
                    WHERE sales_date BETWEEN CURRENT_DATE - 15 AND CURRENT_DATE - 1
                ), 0)::numeric AS sales_15d,
                COALESCE(SUM(volume) FILTER (
                    WHERE sales_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 1
                ), 0)::numeric AS sales_30d
            FROM daily_sales
            WHERE sales_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 1
            GROUP BY sku, amazon_sku, country
        ),
        product_inputs AS (
            SELECT
                product.id AS product_market_parameter_id,
                product.sku,
                product.amazon_sku,
                product.country_code,
                market.name AS country_name,
                product.product_name,
                product.category,
                product.store,
                product.production_lead_days,
                setting.listing_date,
                setting.lifecycle_status,
                setting.forecast_daily_sales_override,
                setting.warehouse_split_ratio,
                setting.notes,
                policy.policy_code,
                policy.west_coast_ocean_days,
                policy.east_coast_ocean_days,
                policy.listing_days,
                policy.fbm_to_fba_transfer_days,
                policy.overall_buffer_days,
                policy.inventory_warning_ratio,
                inventory.snapshot_at,
                COALESCE(inventory.on_hand_qty, 0) AS on_hand_qty,
                COALESCE(inventory.in_transit_qty, 0) AS in_transit_qty,
                COALESCE(inventory.supplier_reserved_qty, 0) AS supplier_reserved_qty,
                COALESCE(inventory.west_warehouse_qty, 0) AS west_warehouse_qty,
                COALESCE(inventory.east_warehouse_qty, 0) AS east_warehouse_qty,
                COALESCE(sales.sales_3d, 0) AS sales_3d,
                COALESCE(sales.sales_7d, 0) AS sales_7d,
                COALESCE(sales.sales_15d, 0) AS sales_15d,
                COALESCE(sales.sales_30d, 0) AS sales_30d
            FROM product_market_parameters AS product
            JOIN market_codes AS market
                ON market.code = product.country_code
            LEFT JOIN replenishment_item_settings AS setting
                ON setting.product_market_parameter_id = product.id
               AND setting.is_active
            JOIN LATERAL (
                SELECT selected_policy.*
                FROM replenishment_policies AS selected_policy
                WHERE selected_policy.is_active
                  AND selected_policy.effective_from <= CURRENT_DATE
                  AND (selected_policy.effective_to IS NULL OR selected_policy.effective_to >= CURRENT_DATE)
                  AND (
                       selected_policy.id = setting.policy_id
                    OR selected_policy.policy_code = 'DEFAULT'
                  )
                ORDER BY (selected_policy.id = setting.policy_id) DESC
                LIMIT 1
            ) AS policy ON TRUE
            LEFT JOIN LATERAL (
                SELECT snapshot.*
                FROM inventory_position_snapshots AS snapshot
                WHERE snapshot.product_market_parameter_id = product.id
                ORDER BY snapshot.snapshot_at DESC
                LIMIT 1
            ) AS inventory ON TRUE
            LEFT JOIN sales
                ON sales.sku = product.sku
               AND sales.amazon_sku = COALESCE(product.amazon_sku, '')
               AND sales.country = market.name
            WHERE product.is_active
        ),
        calculated_sales AS (
            SELECT
                product_inputs.*,
                ROUND(sales_3d / 3, 0) AS avg_sales_3d,
                ROUND(sales_7d / 7, 0) AS avg_sales_7d,
                ROUND(sales_15d / 15, 0) AS avg_sales_15d,
                ROUND(sales_30d / 30, 0) AS avg_sales_30d,
                ROUND(
                    CASE
                        WHEN sales_3d > 0 AND sales_7d > 0 AND sales_15d > 0 AND sales_30d > 0
                        THEN (sales_3d / 3 + sales_7d / 7 + sales_15d / 15 + sales_30d / 30) / 4
                        ELSE sales_30d / 30
                    END,
                    0
                ) AS daily_sales_average
            FROM product_inputs
        ),
        inventory_calculations AS (
            SELECT
                calculated_sales.*,
                on_hand_qty + in_transit_qty + supplier_reserved_qty AS maximum_inventory_qty,
                on_hand_qty + in_transit_qty AS available_inventory_qty,
                daily_sales_average * (
                    COALESCE(production_lead_days, 0) + west_coast_ocean_days + listing_days
                ) AS fba_minimum_safety_stock_qty,
                daily_sales_average * (
                    COALESCE(production_lead_days, 0)
                    + west_coast_ocean_days
                    + listing_days
                    + fbm_to_fba_transfer_days
                ) AS fbm_minimum_safety_stock_qty,
                daily_sales_average * (
                    COALESCE(production_lead_days, 0) + listing_days + west_coast_ocean_days
                ) AS safety_stock_qty
            FROM calculated_sales
        )
        SELECT
            inventory_calculations.*,
            CASE
                WHEN available_inventory_qty <= safety_stock_qty THEN '库存不足'
                WHEN available_inventory_qty >= safety_stock_qty * inventory_warning_ratio THEN '库存预警'
                ELSE '库存正常'
            END AS inventory_status,
            GREATEST(safety_stock_qty - available_inventory_qty, 0) AS recommended_shipment_qty,
            GREATEST(fba_minimum_safety_stock_qty - available_inventory_qty, 0) AS fba_recommended_shipment_qty,
            GREATEST(safety_stock_qty - available_inventory_qty, 0)
                - GREATEST(fba_minimum_safety_stock_qty - available_inventory_qty, 0)
                AS fbm_recommended_shipment_qty,
            CASE
                WHEN snapshot_at IS NULL OR daily_sales_average <= 0 THEN NULL
                ELSE snapshot_at
                    + (
                        available_inventory_qty / daily_sales_average - overall_buffer_days
                    )::double precision * INTERVAL '1 day'
            END AS latest_ship_at,
            GREATEST(
                safety_stock_qty - available_inventory_qty - supplier_reserved_qty,
                0
            ) AS recommended_purchase_qty
        FROM inventory_calculations
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS replenishment_recommendations")
    op.drop_index("ix_inventory_position_product_snapshot", table_name="inventory_position_snapshots")
    op.drop_table("inventory_position_snapshots")
    op.drop_table("replenishment_item_settings")
    op.drop_table("replenishment_policies")
