"""Use FBA fulfillable quantity for the normalized available inventory field."""

from alembic import op


revision = "0013_fix_inventory_available"
down_revision = "0012_lingxing_analysis_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing snapshots retain the complete source response in raw_payload. Rebuild
    # the normalized value so historical and newly synced rows use the same meaning.
    op.execute(
        """
        UPDATE lingxing_inventory_snapshots
        SET available_qty = COALESCE(
            NULLIF(raw_payload->>'afn_fulfillable_quantity', '')::numeric,
            NULLIF(raw_payload->>'available_total', '')::numeric
        )
        WHERE raw_payload ? 'afn_fulfillable_quantity'
           OR raw_payload ? 'available_total'
        """
    )


def downgrade() -> None:
    # Restore the previous normalization rule when rolling back.
    op.execute(
        """
        UPDATE lingxing_inventory_snapshots
        SET available_qty = COALESCE(
            NULLIF(raw_payload->>'available_total', '')::numeric,
            NULLIF(raw_payload->>'afn_fulfillable_quantity', '')::numeric
        )
        WHERE raw_payload ? 'afn_fulfillable_quantity'
           OR raw_payload ? 'available_total'
        """
    )
