"""Synchronize LingXing Listing data into the local raw/core tables.

The synchronizer deliberately keeps the source payload and a batch record. It
only owns the ``lingxing_*`` tables; company parameters and lifecycle fields
remain outside of the sync boundary.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.mcp_client import StreamableHttpMcpClient
from app.db.models import (
    LingXingListing,
    LingXingListingCurrent,
    LingXingListingSnapshot,
    LingXingMarket,
    LingXingMskuProduct,
    LingXingRawRecord,
    LingXingStore,
    LingXingSyncBatch,
    ProductMarketParameter,
)
from app.db.session import SessionLocal


class LingXingSyncError(RuntimeError):
    """Raised when a sync response cannot be safely normalized."""


@dataclass(frozen=True)
class LingXingSyncSummary:
    batch_id: str
    pages: int
    rows: int
    reported_total: int | None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _trace_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("traceId", "trace_id", "request_id", "require_id"):
            value = _text(payload.get(key))
            if value:
                return value
        for value in payload.values():
            found = _trace_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _trace_id(value)
            if found:
                return found
    return None


def extract_list_payload(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    """Unwrap the different envelopes used by direct and gateway MCP calls."""

    node = payload
    if isinstance(node, dict):
        for _ in range(4):
            row_values = next(
                (node[key] for key in ("list", "items", "rows") if isinstance(node.get(key), list)),
                None,
            )
            if row_values is not None:
                rows = [row for row in row_values if isinstance(row, dict)]
                total = node.get("total")
                try:
                    total = int(total) if total is not None else None
                except (TypeError, ValueError):
                    total = None
                return rows, total
            nested = node.get("data")
            if isinstance(nested, (dict, list)):
                node = nested
                continue
            break
    if isinstance(node, list):
        return [row for row in node if isinstance(row, dict)], None
    return [], None


def _payload_error(payload: Any) -> str | None:
    """Return a business-error message found in an otherwise valid MCP payload."""

    if isinstance(payload, dict):
        code = payload.get("code")
        if isinstance(code, str) and code.isdigit():
            code = int(code)
        if isinstance(code, (int, float)) and code not in (0, 1, 200):
            return _text(payload.get("message") or payload.get("msg") or payload.get("error")) or f"业务错误 code={code}"
        for key in ("error", "errors"):
            value = payload.get(key)
            if value:
                return _text(value) or "领星 MCP 返回业务错误"
        for value in payload.values():
            found = _payload_error(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _payload_error(value)
            if found:
                return found
    return None


def _country_code(row: dict[str, Any], store: LingXingStore | None) -> str | None:
    if store and store.country_code:
        return store.country_code.upper()
    marketplace = _text(row.get("marketplace"))
    return {
        "美国": "US",
        "加拿大": "CA",
        "英国": "UK",
        "德国": "DE",
        "法国": "FR",
        "意大利": "IT",
        "西班牙": "ES",
        "荷兰": "NL",
        "比利时": "BE",
        "瑞典": "SE",
        "波兰": "PL",
        "土耳其": "TR",
        "墨西哥": "MX",
    }.get(marketplace or "")


class LingXingListingSync:
    """Pull and normalize ``erp_listing`` into the local database."""

    TOOL_ID = "erp_listing"
    PAGE_SIZE = 200

    def __init__(
        self,
        client: StreamableHttpMcpClient | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
        clock: Callable[[], datetime] | None = None,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self.client = client or StreamableHttpMcpClient(
            settings.LINGXING_MCP_URL,
            settings.LINGXING_MCP_KEY,
        )
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.page_size = page_size
        self._msku_cache: dict[str, LingXingMskuProduct] = {}
        self._market_cache: dict[tuple[str, int], LingXingMarket] = {}
        self._listing_cache: dict[int, LingXingListing] = {}
        self._current_cache: dict[uuid.UUID, LingXingListingCurrent] = {}
        self._pmp_cache: dict[tuple[str, str, str], uuid.UUID] = {}

    async def run(self) -> LingXingSyncSummary:
        if self.page_size not in {20, 50, 100, 200, 500, 1000, 2000, 5000}:
            raise LingXingSyncError("领星 erp_listing 页大小不在允许范围内")

        session = self.session_factory()
        started_at = self.clock()
        batch = LingXingSyncBatch(
            tool_id=self.TOOL_ID,
            request_params={
                "page_size": self.page_size,
                "sort_field": "id",
                "sort_type": "asc",
            },
            started_at=started_at,
        )
        session.add(batch)
        session.commit()

        try:
            stores = await self._sync_stores(session)
            session.commit()
            self._msku_cache = {item.msku: item for item in session.scalars(select(LingXingMskuProduct))}
            self._market_cache = {
                (item.marketplace_id, int(item.mid)): item for item in session.scalars(select(LingXingMarket))
            }
            self._listing_cache = {
                int(item.lingxing_listing_id): item for item in session.scalars(select(LingXingListing))
            }
            self._current_cache = {item.listing_id: item for item in session.scalars(select(LingXingListingCurrent))}
            self._pmp_cache = {
                (item.sku, item.country_code, item.amazon_sku): item.id
                for item in session.scalars(select(ProductMarketParameter))
                if item.amazon_sku
            }
            offset = 0
            pages = 0
            rows_seen = 0
            reported_total: int | None = None
            seen_listing_ids: set[int] = set()

            while True:
                request = {
                    "offset": offset,
                    "length": self.page_size,
                    "pvi_ids": "",
                    "sort_field": "id",
                    "sort_type": "asc",
                }
                payload = await self.client.call_tool(self.TOOL_ID, request)
                payload_error = _payload_error(payload)
                page, page_total = extract_list_payload(payload)
                if page_total is not None:
                    reported_total = page_total
                if not page:
                    if payload_error:
                        raise LingXingSyncError(payload_error)
                    if pages == 0:
                        raise LingXingSyncError("领星 erp_listing 没有返回可同步的列表")
                    break

                for row in page:
                    listing_id = _positive_int(row.get("id"))
                    msku = _text(row.get("msku"))
                    asin = _text(row.get("asin") or row.get("amz_product_id"))
                    source_store_id = _positive_int(row.get("store_id"))
                    source_marketplace_id = _text(row.get("marketplace_id"))
                    if not listing_id or not msku or not asin or not source_store_id or not source_marketplace_id:
                        raise LingXingSyncError(
                            "erp_listing 记录缺少 id/msku/asin/store_id/marketplace_id，已停止同步"
                        )
                    if listing_id in seen_listing_ids:
                        raise LingXingSyncError(f"erp_listing 分页出现重复 Listing ID：{listing_id}")
                    seen_listing_ids.add(listing_id)
                    store = stores.get(source_store_id)
                    self._upsert_listing(session, row, batch, store, started_at)
                    rows_seen += 1

                pages += 1
                batch.page_count = pages
                batch.row_count = rows_seen
                trace_id = _trace_id(payload)
                if trace_id and trace_id not in (batch.trace_ids or []):
                    batch.trace_ids = [*(batch.trace_ids or []), trace_id]
                session.commit()

                offset += self.page_size
                if len(page) < self.page_size:
                    break

            # Only a complete-looking full scan may deactivate rows not seen in
            # this batch. Failed/partial scans never make data disappear.
            session.execute(
                update(LingXingListing)
                .where(LingXingListing.last_seen_at < started_at)
                .values(is_active=False)
            )
            batch.status = "succeeded"
            batch.finished_at = self.clock()
            batch.page_count = pages
            batch.row_count = rows_seen
            session.commit()
            return LingXingSyncSummary(str(batch.id), pages, rows_seen, reported_total)
        except Exception as exc:
            session.rollback()
            failed_batch = session.get(LingXingSyncBatch, batch.id)
            if failed_batch is not None:
                failed_batch.status = "failed"
                failed_batch.error_message = str(exc)[:4000]
                failed_batch.finished_at = self.clock()
                session.commit()
            raise
        finally:
            session.close()

    async def _sync_stores(self, session: Session) -> dict[int, LingXingStore]:
        """Refresh the small store dimension before listing pages are pulled."""

        payload = await self.client.call_tool("get_my_sids", {})
        rows, _ = extract_list_payload(payload)
        if not rows:
            raise LingXingSyncError("领星 get_my_sids 没有返回店铺列表")

        stores: dict[int, LingXingStore] = {}
        now = self.clock()
        for row in rows:
            sid = _positive_int(row.get("sid") or row.get("id") or row.get("store_id"))
            if not sid:
                continue
            store = session.scalar(select(LingXingStore).where(LingXingStore.sid == sid))
            if store is None:
                store = LingXingStore(sid=sid, store_name=_text(row.get("name") or row.get("store_name")) or str(sid))
                session.add(store)
            store.seller_id = _text(row.get("seller_id") or row.get("sellerId"))
            store.store_name = _text(row.get("name") or row.get("store_name") or row.get("seller_name")) or str(sid)
            store.country_code = (_text(row.get("country_code") or row.get("country")) or "").upper() or None
            store.platform_code = _positive_int(row.get("platform_code") or row.get("platformCode")) or 10001
            store.currency = _text(row.get("currency") or row.get("currency_code"))
            store.status = _text(row.get("status") or row.get("state"))
            store.raw_payload = dict(row)
            if store.first_seen_at is None:
                store.first_seen_at = now
            store.last_seen_at = now
            stores[sid] = store
        if not stores:
            raise LingXingSyncError("领星 get_my_sids 返回的店铺记录缺少 sid")
        session.flush()
        return stores

    def _upsert_listing(
        self,
        session: Session,
        row: dict[str, Any],
        batch: LingXingSyncBatch,
        store: LingXingStore | None,
        synced_at: datetime,
    ) -> None:
        listing_id = _positive_int(row.get("id"))
        msku = _text(row.get("msku"))
        asin = _text(row.get("asin") or row.get("amz_product_id"))
        source_store_id = _positive_int(row.get("store_id"))
        source_marketplace_id = _text(row.get("marketplace_id"))
        if not listing_id or not msku or not asin or not source_store_id or not source_marketplace_id:
            raise LingXingSyncError("erp_listing 记录缺少核心业务键")

        if store is None:
            # A listing can remain visible briefly after a store is removed from
            # get_my_sids. Keep the row linkable instead of dropping the listing.
            store = session.scalar(select(LingXingStore).where(LingXingStore.sid == source_store_id))
            if store is None:
                store = LingXingStore(
                    id=uuid.uuid4(),
                    sid=source_store_id,
                    store_name=_text(row.get("store_name") or row.get("shop_name")) or str(source_store_id),
                    platform_code=10001,
                    first_seen_at=synced_at,
                    last_seen_at=synced_at,
                )
                session.add(store)
                session.flush()

        msku_product = self._msku_cache.get(msku)
        if msku_product is None:
            msku_product = LingXingMskuProduct(id=uuid.uuid4(), msku=msku, first_seen_at=synced_at, last_seen_at=synced_at)
            session.add(msku_product)
            self._msku_cache[msku] = msku_product
        source_product_id = _positive_int(row.get("product_id"))
        if source_product_id is not None:
            msku_product.lingxing_product_id = source_product_id
        msku_product.local_sku = _text(row.get("local_sku") or row.get("sku")) or msku_product.local_sku
        msku_product.local_name = _text(row.get("local_name") or row.get("product_name")) or msku_product.local_name
        msku_product.brand = _text(row.get("brand")) or msku_product.brand
        msku_product.principal_uid = _positive_int(row.get("principal_uid") or row.get("principal_id")) or msku_product.principal_uid
        msku_product.principal_name = _text(row.get("principal_name") or row.get("principal")) or msku_product.principal_name
        msku_product.is_active = True
        msku_product.last_seen_at = synced_at
        msku_product.raw_payload = dict(row)
        mid = _positive_int(row.get("mid") or row.get("market_id"))
        if mid is None:
            raise LingXingSyncError(f"erp_listing {listing_id} 缺少 mid，无法建立市场维度")
        market = self._market_cache.get((source_marketplace_id, mid))
        if market is None:
            market = LingXingMarket(id=uuid.uuid4(), mid=mid, marketplace_id=source_marketplace_id)
            session.add(market)
            self._market_cache[(source_marketplace_id, mid)] = market
        market.country_code = _country_code(row, store)
        market.marketplace_name = _text(row.get("marketplace_name") or row.get("marketplace"))
        market.site_url = _text(row.get("asin_url") or row.get("site_url"))
        market.currency = _text(row.get("currency_symbol") or row.get("listing_price_currency_code") or row.get("currency"))
        market.raw_payload = {"marketplace_id": source_marketplace_id, "mid": mid, **dict(row)}
        market.last_seen_at = synced_at
        local_sku = _text(row.get("local_sku") or row.get("sku"))
        pmp_id = None
        country_code = _country_code(row, store)
        if local_sku and country_code:
            pmp_id = self._pmp_cache.get((local_sku, country_code, msku))

        listing = self._listing_cache.get(listing_id)
        if listing is None:
            listing = LingXingListing(
                id=uuid.uuid4(),
                lingxing_listing_id=listing_id,
                msku_product_id=msku_product.id,
                source_store_id=source_store_id,
                source_marketplace_id=source_marketplace_id,
                asin=asin,
                first_seen_at=synced_at,
            )
            session.add(listing)
            self._listing_cache[listing_id] = listing
        listing.msku_product_id = msku_product.id
        listing.product_market_parameter_id = pmp_id
        listing.store_id = store.id
        listing.market_id = market.id
        listing.source_store_id = source_store_id
        listing.source_marketplace_id = source_marketplace_id
        listing.asin = asin
        listing.parent_asin = _text(row.get("parent_asin"))
        listing.fnsku = _text(row.get("fnsku"))
        listing.local_sku = local_sku
        listing.fulfillment_channel_type = _text(row.get("fulfillment_channel_type") or row.get("fulfillment_channel"))
        listing.status = _positive_int(row.get("status"))
        listing.status_text = _text(row.get("status_text") or row.get("status_name"))
        listing.item_name = _text(row.get("item_name") or row.get("product_name"))
        listing.variant_text = row.get("variant") if isinstance(row.get("variant"), list) else None
        listing.seller_category = row.get("seller_category") if isinstance(row.get("seller_category"), list) else None
        listing.first_order_time = _text(row.get("first_order_time"))
        listing.open_date_time = _text(row.get("open_date_time"))
        listing.on_sale_time = _text(row.get("on_sale_time"))
        listing.is_active = True
        listing.last_seen_at = synced_at
        listing.raw_payload = dict(row)
        raw = LingXingRawRecord(
            id=uuid.uuid4(),
            sync_batch_id=batch.id,
            tool_id=self.TOOL_ID,
            source_record_key=str(listing_id),
            payload=dict(row),
            payload_hash=_payload_hash(row),
            fetched_at=synced_at,
        )
        session.add(raw)

        current = self._current_cache.get(listing.id)
        if current is None:
            current = LingXingListingCurrent(listing_id=listing.id, as_of_at=synced_at, updated_at=synced_at)
            session.add(current)
            self._current_cache[listing.id] = current
        current.currency_code = _text(row.get("listing_price_currency_code") or row.get("currency_code") or market.currency)
        for attr, keys in {
            "listing_price": ("listing_price", "price"),
            "regular_price": ("regular_price",),
            "landed_price": ("landed_price",),
            "fba_fee": ("fba_fee",),
            "referral_fee": ("referral_fee",),
            "afn_fulfillable_quantity": ("afn_fulfillable_quantity", "afn_fulfillable"),
            "afn_reserved_quantity": ("afn_reserved_quantity", "afn_reserved"),
            "afn_unsellable_quantity": ("afn_unsellable_quantity", "afn_unsellable"),
            "afn_inbound_working_quantity": ("afn_inbound_working_quantity", "afn_inbound_working"),
            "afn_inbound_shipped_quantity": ("afn_inbound_shipped_quantity", "afn_inbound_shipped"),
            "afn_inbound_receiving_quantity": ("afn_inbound_receiving_quantity", "afn_inbound_receiving"),
            "fbm_quantity": ("fbm_quantity", "quantity"),
        }.items():
            value = next((row.get(key) for key in keys if row.get(key) not in (None, "")), None)
            setattr(current, attr, _decimal(value))
        current.seller_rank = _positive_int(row.get("seller_rank") or row.get("rank"))
        current.stars = _decimal(row.get("stars") or row.get("star"))
        current.reviews_num = _positive_int(row.get("reviews_num") or row.get("review_count"))
        current.as_of_at = synced_at
        current.updated_at = synced_at

        selected = {
            key: row.get(key)
            for key in (
                "id", "msku", "asin", "listing_price", "regular_price", "landed_price",
                "listing_price_currency_code", "afn_fulfillable_quantity", "afn_reserved_quantity",
                "afn_unsellable_quantity", "quantity", "seller_rank", "stars", "reviews_num", "status",
            )
            if key in row
        }
        session.add(
            LingXingListingSnapshot(
                id=uuid.uuid4(),
                listing_id=listing.id,
                sync_batch_id=batch.id,
                snapshot_at=synced_at,
                payload_hash=_payload_hash(selected),
                selected_metrics=selected,
            )
        )
