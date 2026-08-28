"""Track the current product lifecycle node on the product master row."""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_lifecycle_node_code"
down_revision = "0004_inventory_source_components"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_market_parameters",
        sa.Column("lifecycle_node_code", sa.String(16), server_default="P01", nullable=False),
    )
    op.create_index(
        "ix_product_market_parameters_lifecycle_node_code",
        "product_market_parameters",
        ["lifecycle_node_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_market_parameters_lifecycle_node_code",
        table_name="product_market_parameters",
    )
    op.drop_column("product_market_parameters", "lifecycle_node_code")
