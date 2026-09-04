from app.db.models import (
    LingXingListing,
    LingXingListingCurrent,
    LingXingListingSnapshot,
    LingXingInventorySnapshot,
    LingXingMarket,
    LingXingMskuProduct,
    LingXingProfitFact,
    LingXingRawRecord,
    LingXingSalesDaily,
    LingXingStore,
    LingXingSyncBatch,
)


def _constraint_names(table):
    return {constraint.name for constraint in table.constraints if constraint.name}


def test_lingxing_core_tables_are_registered():
    assert {
        LingXingSyncBatch.__tablename__,
        LingXingRawRecord.__tablename__,
        LingXingStore.__tablename__,
        LingXingMarket.__tablename__,
        LingXingMskuProduct.__tablename__,
        LingXingListing.__tablename__,
        LingXingListingCurrent.__tablename__,
        LingXingListingSnapshot.__tablename__,
        LingXingSalesDaily.__tablename__,
        LingXingInventorySnapshot.__tablename__,
        LingXingProfitFact.__tablename__,
    } <= set(LingXingSyncBatch.metadata.tables)


def test_msku_is_unique_but_listing_has_separate_source_identity():
    assert LingXingMskuProduct.__table__.c.msku.unique is True
    assert LingXingListing.__table__.c.lingxing_listing_id.unique is True
    assert "uq_lingxing_listings_business_identity" in _constraint_names(LingXingListing.__table__)


def test_listing_preserves_product_market_parameter_compatibility_link():
    foreign_keys = {
        fk.target_fullname for column in LingXingListing.__table__.columns for fk in column.foreign_keys
    }
    assert "product_market_parameters.id" in foreign_keys
    assert LingXingListing.__table__.c.product_market_parameter_id.nullable is True


def test_current_metrics_are_one_to_one_and_snapshots_are_batch_unique():
    assert LingXingListingCurrent.__table__.primary_key.columns.keys() == ["listing_id"]
    assert "uq_lingxing_listing_snapshot_batch" in _constraint_names(LingXingListingSnapshot.__table__)
    assert "ix_lingxing_listing_snapshots_listing_time" in {
        index.name for index in LingXingListingSnapshot.__table__.indexes
    }


def test_fact_tables_include_query_grain_in_their_idempotency_keys():
    assert "uq_lingxing_sales_daily_source_row" in _constraint_names(LingXingSalesDaily.__table__)
    assert "uq_lingxing_inventory_snapshot_source_row" in _constraint_names(LingXingInventorySnapshot.__table__)
    assert "uq_lingxing_profit_fact_source_row" in _constraint_names(LingXingProfitFact.__table__)
    assert LingXingSalesDaily.__table__.c.query_fingerprint.nullable is False
    assert LingXingProfitFact.__table__.c.summary_field.nullable is False
