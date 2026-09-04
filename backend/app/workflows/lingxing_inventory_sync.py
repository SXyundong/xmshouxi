"""Synchronize FBA inventory rows from LingXing into point-in-time facts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.mcp_client import StreamableHttpMcpClient
from app.db.models import (
    LingXingInventorySnapshot,
    LingXingListing,
    LingXingMarket,
    LingXingMskuProduct,
    LingXingRawRecord,
    LingXingStore,
    LingXingSyncBatch,
)
from app.db.session import SessionLocal
from app.workflows.lingxing_listing_sync import (
    LingXingSyncError,
    _decimal,
    _payload_error,
    _payload_hash,
    _positive_int,
    _text,
    extract_list_payload,
)


class LingXingInventorySync:
    TOOL_ID = "get_fba_stock_list"
    PAGE_SIZE = 100

    def __init__(
        self,
        client: StreamableHttpMcpClient | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client or StreamableHttpMcpClient(
            settings.LINGXING_MCP_URL,
            settings.LINGXING_MCP_KEY,
        )
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def run(
        self,
        sids: list[int] | None = None,
        msku: str | None = None,
        page_size: int = PAGE_SIZE,
    ) -> dict[str, Any]:
        if page_size not in {20, 50, 100, 200, 500, 1000, 2000, 5000}:
            raise LingXingSyncError("FBA库存接口页大小不在允许范围内")

        session = self.session_factory()
        snapshot_at = self.clock()
        stores = list(session.scalars(select(LingXingStore)))
        sid_values = sids or [int(store.sid) for store in stores]
        if not sid_values:
            raise LingXingSyncError("本地没有店铺维度，无法确定 FBA 库存查询范围")
        batch = LingXingSyncBatch(
            tool_id=self.TOOL_ID,
            request_params={"sids": sid_values, "msku": msku, "page_size": page_size},
            started_at=snapshot_at,
        )
        session.add(batch)
        session.commit()

        msku_cache = {item.msku: item for item in session.scalars(select(LingXingMskuProduct))}
        listing_cache = {(item.msku_product_id, item.asin): item for item in session.scalars(select(LingXingListing))}
        store_cache = {int(item.sid): item for item in stores}
        market_cache = {int(item.mid): item for item in session.scalars(select(LingXingMarket))}
        rows_written = 0
        pages = 0
        try:
            for sid in sid_values:
                offset = 0
                while True:
                    request = {
                        "offset": offset,
                        "length": page_size,
                        "sort_field": "sku",
                        "sort_type": "asc",
                        "is_cost_page": "0",
                        "fulfillment_channel_type": "FBA",
                        "search_field": "seller_sku",
                        "search_value": msku or "",
                        "sid": str(sid),
                        "wids": "",
                    }
                    payload = await self.client.call_tool(self.TOOL_ID, request)
                    error = _payload_error(payload)
                    rows, reported_total = extract_list_payload(payload)
                    if error and not rows:
                        raise LingXingSyncError(error)
                    if not rows:
                        break

                    for row in rows:
                        seller_sku = _text(row.get("seller_sku"))
                        asin = _text(row.get("asin") or row.get("parent_asin_real"))
                        row_key = _payload_hash({"sid": sid, "row": row})
                        msku_product = msku_cache.get(seller_sku) if seller_sku else None
                        listing = listing_cache.get((msku_product.id, asin)) if msku_product and asin else None
                        fingerprint = _payload_hash(request)
                        existing = session.scalar(
                            select(LingXingInventorySnapshot).where(
                                LingXingInventorySnapshot.snapshot_at == snapshot_at,
                                LingXingInventorySnapshot.query_fingerprint == fingerprint,
                                LingXingInventorySnapshot.source_row_key == row_key,
                            )
                        )
                        values = {
                            "msku_product_id": msku_product.id if msku_product else None,
                            "listing_id": listing.id if listing else None,
                            "store_id": store_cache.get(_positive_int(row.get("sid")) or sid).id
                            if store_cache.get(_positive_int(row.get("sid")) or sid)
                            else None,
                            "market_id": market_cache.get(_positive_int(row.get("mid"))).id
                            if market_cache.get(_positive_int(row.get("mid")))
                            else None,
                            "warehouse_external_id": _text(row.get("wids") or row.get("warehouse_id")),
                            "inventory_source": "fba",
                            "query_fingerprint": fingerprint,
                            "source_row_key": row_key,
                            "available_qty": _decimal(_first(row, "available_total", "afn_fulfillable_quantity")),
                            "reserved_qty": _decimal(_first(row, "afn_reserved_quantity", "reserved_customerorders")),
                            "inbound_working_qty": _decimal(row.get("afn_inbound_working_quantity")),
                            "inbound_shipped_qty": _decimal(row.get("afn_inbound_shipped_quantity")),
                            "inbound_receiving_qty": _decimal(row.get("afn_inbound_receiving_quantity")),
                            "unsellable_qty": _decimal(row.get("afn_unsellable_quantity")),
                            "age_buckets": {
                                key: value
                                for key, value in row.items()
                                if key.startswith("inv_age_") and not key.endswith("_price")
                            },
                            "amounts": {
                                key: value
                                for key, value in row.items()
                                if key.endswith("_price")
                            },
                            "raw_payload": dict(row),
                            "sync_batch_id": batch.id,
                            "fetched_at": snapshot_at,
                        }
                        if existing is None:
                            session.add(
                                LingXingInventorySnapshot(
                                    id=uuid.uuid4(),
                                    snapshot_at=snapshot_at,
                                    **values,
                                )
                            )
                        else:
                            for key, value in values.items():
                                setattr(existing, key, value)
                        session.add(
                            LingXingRawRecord(
                                id=uuid.uuid4(),
                                sync_batch_id=batch.id,
                                tool_id=self.TOOL_ID,
                                source_record_key=row_key,
                                payload=dict(row),
                                payload_hash=_payload_hash(row),
                                fetched_at=snapshot_at,
                            )
                        )
                        rows_written += 1

                    pages += 1
                    batch.page_count = pages
                    batch.row_count = rows_written
                    session.commit()
                    offset += page_size
                    if len(rows) < page_size or (reported_total is not None and offset >= reported_total):
                        break

            batch.status = "succeeded"
            batch.finished_at = self.clock()
            session.commit()
            return {"batch_id": str(batch.id), "pages": pages, "rows": rows_written, "sids": sid_values}
        except Exception as exc:
            session.rollback()
            failed = session.get(LingXingSyncBatch, batch.id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:4000]
                failed.finished_at = self.clock()
                session.commit()
            raise
        finally:
            session.close()


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)
