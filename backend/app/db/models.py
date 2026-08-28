"""Canonical product master data models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
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
