"""Retain inventory source components used to calculate canonical in-transit stock."""

from alembic import op
import sqlalchemy as sa


revision = "0004_inventory_source_components"
down_revision = "0003_replenishment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_position_snapshots",
        sa.Column("fba_plan_inbound_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column(
        "inventory_position_snapshots",
        sa.Column("fba_shipped_in_transit_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column(
        "inventory_position_snapshots",
        sa.Column("fba_receiving_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column(
        "inventory_position_snapshots",
        sa.Column("aglc_shipped_qty", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column("inventory_position_snapshots", sa.Column("source_row", sa.Integer()))


def downgrade() -> None:
    op.drop_column("inventory_position_snapshots", "source_row")
    op.drop_column("inventory_position_snapshots", "aglc_shipped_qty")
    op.drop_column("inventory_position_snapshots", "fba_receiving_qty")
    op.drop_column("inventory_position_snapshots", "fba_shipped_in_transit_qty")
    op.drop_column("inventory_position_snapshots", "fba_plan_inbound_qty")
