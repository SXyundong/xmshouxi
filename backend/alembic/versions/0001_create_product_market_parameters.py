"""Create market dictionary and canonical product parameter table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_product_market_parameters"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "market_codes",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(
        sa.table(
            "market_codes",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
        ),
        [
            {"code": "US", "name": "美国"},
            {"code": "CA", "name": "加拿大"},
            {"code": "UK", "name": "英国"},
            {"code": "DE", "name": "德国"},
            {"code": "EU", "name": "欧洲"},
        ],
    )
    op.create_table(
        "product_market_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        sa.Column("amazon_sku", sa.String(length=100), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("store", sa.String(length=255), nullable=True),
        sa.Column("unit_length_cm", sa.Numeric(12, 3)),
        sa.Column("unit_width_cm", sa.Numeric(12, 3)),
        sa.Column("unit_height_cm", sa.Numeric(12, 3)),
        sa.Column("unit_weight_g", sa.Numeric(12, 3)),
        sa.Column("unit_weight_kg", sa.Numeric(12, 6)),
        sa.Column("carton_length_cm", sa.Numeric(12, 3)),
        sa.Column("carton_width_cm", sa.Numeric(12, 3)),
        sa.Column("carton_height_cm", sa.Numeric(12, 3)),
        sa.Column("carton_quantity", sa.Integer()),
        sa.Column("carton_weight_kg", sa.Numeric(12, 6)),
        sa.Column("carton_volume_m3", sa.Numeric(14, 8)),
        sa.Column("unit_name", sa.String(length=32)),
        sa.Column("purchase_cost_cny", sa.Numeric(18, 4)),
        sa.Column("production_lead_days", sa.Integer()),
        sa.Column("name_zh", sa.Text()),
        sa.Column("name_en", sa.Text()),
        sa.Column("customs_name", sa.Text()),
        sa.Column("name_bilingual", sa.Text()),
        sa.Column("invoice_unit", sa.String(length=32)),
        sa.Column("hs_code", sa.String(length=64)),
        sa.Column("declaration_elements", sa.Text()),
        sa.Column("packaging_method", sa.String(length=255)),
        sa.Column("supplier", sa.String(length=255)),
        sa.Column("material_en", sa.Text()),
        sa.Column("material_zh", sa.Text()),
        sa.Column("usage_en", sa.Text()),
        sa.Column("customs_code", sa.String(length=64)),
        sa.Column("brand", sa.String(length=255)),
        sa.Column("material_bilingual", sa.Text()),
        sa.Column("usage_bilingual", sa.Text()),
        sa.Column("domestic_purchase_price_cny", sa.Numeric(18, 4)),
        sa.Column("declared_price_usd", sa.Numeric(18, 4)),
        sa.Column("declared_price", sa.Numeric(18, 4)),
        sa.Column("agl_declared_price", sa.Numeric(18, 4)),
        sa.Column("source_file", sa.Text()),
        sa.Column("source_sheet", sa.String(length=255)),
        sa.Column("source_row", sa.Integer()),
        sa.Column("import_batch_id", sa.String(length=64)),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["country_code"], ["market_codes.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", "country_code", "amazon_sku", name="uq_product_market_parameters_business_key"),
    )
    op.create_index(
        "ix_product_market_parameters_sku_country",
        "product_market_parameters",
        ["sku", "country_code"],
    )
    op.create_index(
        "ix_product_market_parameters_amazon_sku",
        "product_market_parameters",
        ["amazon_sku"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_market_parameters_amazon_sku", table_name="product_market_parameters")
    op.drop_index("ix_product_market_parameters_sku_country", table_name="product_market_parameters")
    op.drop_table("product_market_parameters")
    op.drop_table("market_codes")
