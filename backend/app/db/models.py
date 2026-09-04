"""Canonical product master data models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class MarketCode(Base):
    __tablename__ = "market_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    products: Mapped[list[ProductMarketParameter]] = relationship(back_populates="market")


class ProductMarketParameter(Base):
    """One concrete SKU/market/MSKU product listing with its master parameters."""

    __tablename__ = "product_market_parameters"
    __table_args__ = (
        UniqueConstraint(
            "sku",
            "country_code",
            "amazon_sku",
            name="uq_product_market_parameters_business_key",
        ),
        Index("ix_product_market_parameters_sku_country", "sku", "country_code"),
        Index("ix_product_market_parameters_amazon_sku", "amazon_sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("market_codes.code", ondelete="RESTRICT"), nullable=False
    )
    amazon_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    store: Mapped[str | None] = mapped_column(String(255))

    unit_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    carton_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    carton_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    carton_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    carton_quantity: Mapped[int | None] = mapped_column(Integer)
    carton_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    carton_volume_m3: Mapped[Decimal | None] = mapped_column(Numeric(14, 8))
    unit_name: Mapped[str | None] = mapped_column(String(32))

    purchase_cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    production_lead_days: Mapped[int | None] = mapped_column(Integer)
    name_zh: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    customs_name: Mapped[str | None] = mapped_column(Text)
    name_bilingual: Mapped[str | None] = mapped_column(Text)
    invoice_unit: Mapped[str | None] = mapped_column(String(32))
    hs_code: Mapped[str | None] = mapped_column(String(64))
    declaration_elements: Mapped[str | None] = mapped_column(Text)
    packaging_method: Mapped[str | None] = mapped_column(String(255))
    supplier: Mapped[str | None] = mapped_column(String(255))
    material_en: Mapped[str | None] = mapped_column(Text)
    material_zh: Mapped[str | None] = mapped_column(Text)
    usage_en: Mapped[str | None] = mapped_column(Text)
    customs_code: Mapped[str | None] = mapped_column(String(64))
    brand: Mapped[str | None] = mapped_column(String(255))
    material_bilingual: Mapped[str | None] = mapped_column(Text)
    usage_bilingual: Mapped[str | None] = mapped_column(Text)
    domestic_purchase_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    declared_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    declared_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    agl_declared_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    source_file: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)
    import_batch_id: Mapped[str | None] = mapped_column(String(64))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lifecycle_node_code: Mapped[str] = mapped_column(
        String(16), nullable=False, default="P01", server_default="P01"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    market: Mapped[MarketCode] = relationship(back_populates="products")
    replenishment_settings: Mapped[ReplenishmentItemSetting | None] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    inventory_snapshots: Mapped[list[InventoryPositionSnapshot]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class LingXingSyncBatch(Base):
    """One read-only LingXing extraction run, including pagination metadata."""

    __tablename__ = "lingxing_sync_batches"
    __table_args__ = (
        Index("ix_lingxing_sync_batches_tool_started", "tool_id", "started_at"),
        Index("ix_lingxing_sync_batches_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    catalog_version: Mapped[str | None] = mapped_column(String(128))
    schema_version: Mapped[str | None] = mapped_column(String(128))
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", server_default="running")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    trace_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_records: Mapped[list[LingXingRawRecord]] = relationship(
        back_populates="sync_batch",
        cascade="all, delete-orphan",
    )
    listing_snapshots: Mapped[list[LingXingListingSnapshot]] = relationship(
        back_populates="sync_batch",
        cascade="all, delete-orphan",
    )
    sales_facts: Mapped[list[LingXingSalesDaily]] = relationship(
        back_populates="sync_batch", cascade="all, delete-orphan"
    )
    inventory_facts: Mapped[list[LingXingInventorySnapshot]] = relationship(
        back_populates="sync_batch", cascade="all, delete-orphan"
    )
    profit_facts: Mapped[list[LingXingProfitFact]] = relationship(
        back_populates="sync_batch", cascade="all, delete-orphan"
    )


class LingXingRawRecord(Base):
    """Immutable-ish raw response row retained for replay and schema drift checks."""

    __tablename__ = "lingxing_raw_records"
    __table_args__ = (
        Index("ix_lingxing_raw_records_tool_key", "tool_id", "source_record_key"),
        Index("ix_lingxing_raw_records_batch", "sync_batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_key: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    sync_batch: Mapped[LingXingSyncBatch] = relationship(back_populates="raw_records")


class LingXingStore(Base):
    """LingXing store/seller account dimension."""

    __tablename__ = "lingxing_stores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sid: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    seller_id: Mapped[str | None] = mapped_column(String(128))
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))
    platform_code: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(32))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listings: Mapped[list[LingXingListing]] = relationship(back_populates="store")


class LingXingMarket(Base):
    """LingXing market/site dimension, separate from the company's market_codes."""

    __tablename__ = "lingxing_markets"
    __table_args__ = (
        UniqueConstraint("marketplace_id", "mid", name="uq_lingxing_markets_marketplace_mid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    marketplace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))
    marketplace_name: Mapped[str | None] = mapped_column(String(64))
    site_url: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(16))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listings: Mapped[list[LingXingListing]] = relationship(back_populates="market")


class LingXingMskuProduct(Base):
    """One sellable MSKU product; MSKU is the business-unique key."""

    __tablename__ = "lingxing_msku_products"
    __table_args__ = (
        Index("ix_lingxing_msku_products_local_sku", "local_sku"),
        Index("ix_lingxing_msku_products_source_product", "lingxing_product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    msku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    lingxing_product_id: Mapped[int | None] = mapped_column(BigInteger)
    local_sku: Mapped[str | None] = mapped_column(String(100))
    local_name: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    principal_uid: Mapped[int | None] = mapped_column(BigInteger)
    principal_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    listings: Mapped[list[LingXingListing]] = relationship(
        back_populates="msku_product",
        cascade="all, delete-orphan",
    )


class LingXingListing(Base):
    """One row returned by erp_listing (market/store listing grain)."""

    __tablename__ = "lingxing_listings"
    __table_args__ = (
        UniqueConstraint(
            "msku_product_id",
            "source_store_id",
            "source_marketplace_id",
            "asin",
            name="uq_lingxing_listings_business_identity",
        ),
        Index("ix_lingxing_listings_msku", "msku_product_id"),
        Index("ix_lingxing_listings_store_market", "store_id", "market_id"),
        Index("ix_lingxing_listings_asin", "asin"),
        Index("ix_lingxing_listings_product_market_parameter", "product_market_parameter_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lingxing_listing_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    msku_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("lingxing_msku_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_market_parameter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_market_parameters.id", ondelete="SET NULL"),
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_stores.id", ondelete="SET NULL")
    )
    market_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_markets.id", ondelete="SET NULL")
    )
    source_store_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_marketplace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    asin: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_asin: Mapped[str | None] = mapped_column(String(32))
    fnsku: Mapped[str | None] = mapped_column(String(64))
    local_sku: Mapped[str | None] = mapped_column(String(100))
    fulfillment_channel_type: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[int | None] = mapped_column(Integer)
    status_text: Mapped[str | None] = mapped_column(String(32))
    item_name: Mapped[str | None] = mapped_column(Text)
    variant_text: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    seller_category: Mapped[list[str] | None] = mapped_column(JSONB)
    first_order_time: Mapped[str | None] = mapped_column(String(64))
    open_date_time: Mapped[str | None] = mapped_column(String(64))
    on_sale_time: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    msku_product: Mapped[LingXingMskuProduct] = relationship(back_populates="listings")
    product_market_parameter: Mapped[ProductMarketParameter | None] = relationship()
    store: Mapped[LingXingStore | None] = relationship(back_populates="listings")
    market: Mapped[LingXingMarket | None] = relationship(back_populates="listings")
    current: Mapped[LingXingListingCurrent | None] = relationship(
        back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[LingXingListingSnapshot]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class LingXingListingCurrent(Base):
    """Latest dynamic metrics for one Listing; safe to overwrite on sync."""

    __tablename__ = "lingxing_listing_current"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_listings.id", ondelete="CASCADE"), primary_key=True
    )
    currency_code: Mapped[str | None] = mapped_column(String(16))
    listing_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    landed_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    fba_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    referral_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_fulfillable_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_reserved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_unsellable_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_inbound_working_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_inbound_shipped_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    afn_inbound_receiving_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    fbm_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    seller_rank: Mapped[int | None] = mapped_column(Integer)
    stars: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    reviews_num: Mapped[int | None] = mapped_column(BigInteger)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listing: Mapped[LingXingListing] = relationship(back_populates="current")


class LingXingListingSnapshot(Base):
    """Point-in-time Listing payload for price/inventory/status history."""

    __tablename__ = "lingxing_listing_snapshots"
    __table_args__ = (
        UniqueConstraint("listing_id", "sync_batch_id", name="uq_lingxing_listing_snapshot_batch"),
        Index("ix_lingxing_listing_snapshots_listing_time", "listing_id", "snapshot_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_listings.id", ondelete="CASCADE"), nullable=False
    )
    sync_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    listing: Mapped[LingXingListing] = relationship(back_populates="snapshots")
    sync_batch: Mapped[LingXingSyncBatch] = relationship(back_populates="listing_snapshots")


class LingXingSalesDaily(Base):
    """Daily sales fact at the grain declared by the source query."""

    __tablename__ = "lingxing_sales_daily"
    __table_args__ = (
        UniqueConstraint(
            "sales_date",
            "query_fingerprint",
            "source_row_key",
            name="uq_lingxing_sales_daily_source_row",
        ),
        Index("ix_lingxing_sales_daily_msku_date", "msku_product_id", "sales_date"),
        Index("ix_lingxing_sales_daily_market_date", "market_id", "sales_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sales_date: Mapped[date] = mapped_column(Date, nullable=False)
    msku_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_listings.id", ondelete="SET NULL")
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_stores.id", ondelete="SET NULL")
    )
    market_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_markets.id", ondelete="SET NULL")
    )
    currency_code: Mapped[str | None] = mapped_column(String(16))
    query_grain: Mapped[str] = mapped_column(String(64), nullable=False)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_key: Mapped[str] = mapped_column(String(255), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    order_items: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sync_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    msku_product: Mapped[LingXingMskuProduct | None] = relationship()
    listing: Mapped[LingXingListing | None] = relationship()
    sync_batch: Mapped[LingXingSyncBatch] = relationship(back_populates="sales_facts")


class LingXingInventorySnapshot(Base):
    """Point-in-time inventory fact, retaining warehouse/source dimensions."""

    __tablename__ = "lingxing_inventory_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_at",
            "query_fingerprint",
            "source_row_key",
            name="uq_lingxing_inventory_snapshot_source_row",
        ),
        Index("ix_lingxing_inventory_snapshots_msku_time", "msku_product_id", "snapshot_at"),
        Index("ix_lingxing_inventory_snapshots_source_time", "inventory_source", "snapshot_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    msku_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_listings.id", ondelete="SET NULL")
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_stores.id", ondelete="SET NULL")
    )
    market_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_markets.id", ondelete="SET NULL")
    )
    warehouse_external_id: Mapped[str | None] = mapped_column(String(128))
    inventory_source: Mapped[str] = mapped_column(String(32), nullable=False)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_key: Mapped[str] = mapped_column(String(255), nullable=False)
    available_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reserved_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inbound_working_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inbound_shipped_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inbound_receiving_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unsellable_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    age_buckets: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    amounts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sync_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sync_batch: Mapped[LingXingSyncBatch] = relationship(back_populates="inventory_facts")


class LingXingProfitFact(Base):
    """Profit/fee fact with explicit period and aggregation query grain."""

    __tablename__ = "lingxing_profit_facts"
    __table_args__ = (
        UniqueConstraint(
            "period_start",
            "period_end",
            "query_fingerprint",
            "source_row_key",
            name="uq_lingxing_profit_fact_source_row",
        ),
        Index("ix_lingxing_profit_facts_msku_period", "msku_product_id", "period_start", "period_end"),
        Index("ix_lingxing_profit_facts_currency_period", "currency_code", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    msku_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_msku_products.id", ondelete="SET NULL")
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_listings.id", ondelete="SET NULL")
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_stores.id", ondelete="SET NULL")
    )
    market_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_markets.id", ondelete="SET NULL")
    )
    currency_code: Mapped[str | None] = mapped_column(String(16))
    summary_field: Mapped[str] = mapped_column(String(64), nullable=False)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_key: Mapped[str] = mapped_column(String(255), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    total_costs: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    ad_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sync_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lingxing_sync_batches.id", ondelete="CASCADE"), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sync_batch: Mapped[LingXingSyncBatch] = relationship(back_populates="profit_facts")


class ReplenishmentPolicy(Base):
    """Reusable lead-time and buffer rules used by replenishment calculations."""

    __tablename__ = "replenishment_policies"
    __table_args__ = (
        CheckConstraint("west_coast_ocean_days >= 0", name="ck_replenishment_policy_west_days"),
        CheckConstraint("east_coast_ocean_days >= 0", name="ck_replenishment_policy_east_days"),
        CheckConstraint("listing_days >= 0", name="ck_replenishment_policy_listing_days"),
        CheckConstraint("fbm_to_fba_transfer_days >= 0", name="ck_replenishment_policy_fbm_days"),
        CheckConstraint("overall_buffer_days >= 0", name="ck_replenishment_policy_buffer_days"),
        CheckConstraint("inventory_warning_ratio >= 1", name="ck_replenishment_policy_warning_ratio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    policy_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("market_codes.code", ondelete="RESTRICT")
    )
    store: Mapped[str | None] = mapped_column(String(255))
    channel_type: Mapped[str | None] = mapped_column(String(32))
    west_coast_ocean_days: Mapped[int] = mapped_column(Integer, nullable=False, default=35)
    east_coast_ocean_days: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    listing_days: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    fbm_to_fba_transfer_days: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    overall_buffer_days: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    inventory_warning_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=Decimal("1.5"))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    item_settings: Mapped[list[ReplenishmentItemSetting]] = relationship(back_populates="policy")


class ReplenishmentItemSetting(Base):
    """Manual replenishment inputs belonging to one concrete product listing."""

    __tablename__ = "replenishment_item_settings"
    __table_args__ = (
        CheckConstraint("forecast_daily_sales_override IS NULL OR forecast_daily_sales_override >= 0", name="ck_replenishment_setting_forecast"),
        CheckConstraint("warehouse_split_ratio IS NULL OR (warehouse_split_ratio >= 0 AND warehouse_split_ratio <= 1)", name="ck_replenishment_setting_split_ratio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_market_parameter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_market_parameters.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("replenishment_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_date: Mapped[date | None] = mapped_column(Date)
    lifecycle_status: Mapped[str | None] = mapped_column(String(64))
    forecast_daily_sales_override: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    warehouse_split_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product: Mapped[ProductMarketParameter] = relationship(back_populates="replenishment_settings")
    policy: Mapped[ReplenishmentPolicy] = relationship(back_populates="item_settings")


class InventoryPositionSnapshot(Base):
    """Point-in-time inventory facts; historical snapshots are retained."""

    __tablename__ = "inventory_position_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "product_market_parameter_id",
            "snapshot_at",
            name="uq_inventory_position_product_snapshot",
        ),
        Index(
            "ix_inventory_position_product_snapshot",
            "product_market_parameter_id",
            "snapshot_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_market_parameter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_market_parameters.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    on_hand_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    in_transit_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    supplier_reserved_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    # Source components retained for auditability. The canonical in-transit
    # value is N + O + P from the 20260717 inventory workbook.
    fba_plan_inbound_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    fba_shipped_in_transit_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    fba_receiving_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    aglc_shipped_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    west_warehouse_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    east_warehouse_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    source: Mapped[str | None] = mapped_column(String(64))
    source_batch_id: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product: Mapped[ProductMarketParameter] = relationship(back_populates="inventory_snapshots")


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        Index("ix_chat_conversations_owner_department", "owner_open_id", "department"),
        Index("ix_chat_conversations_owner_updated", "owner_open_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_open_id: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新聊天", server_default="新聊天")
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.sequence_no"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_chat_messages_conversation_sequence"),
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed", server_default="completed")
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    conversation: Mapped[ChatConversation] = relationship(back_populates="messages")
