"""Synchronize daily product-performance rows into LingXing sales facts."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.mcp_client import StreamableHttpMcpClient
from app.db.models import (
    LingXingListing,
    LingXingMskuProduct,
    LingXingRawRecord,
    LingXingSalesDaily,
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


def _as_date(value: Any, fallback: date) -> date:
    text = _text(value)
    if not text:
        return fallback
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return fallback


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)


def _resolve_msku(row: dict[str, Any], requested_mskus: list[str] | None = None) -> str | None:
    """Resolve MSKU from the row or its nested listing price entries.

    The product-performance endpoint can return an ``asin_summary`` row with a
    null top-level ``msku`` even when an MSKU search was applied. In that shape,
    ``price_list`` carries the seller SKU for each listing. Only use a requested
    MSKU when it is explicitly present in those nested entries; never infer an
    arbitrary MSKU from an unrelated ASIN aggregate.
    """

    direct = _text(_first(row, "msku", "seller_sku", "sellerSku", "merchant_sku"))
    if direct:
        return direct
    nested = {
        _text(item.get("seller_sku"))
        for item in row.get("price_list", [])
        if isinstance(item, dict) and _text(item.get("seller_sku"))
    }
    requested = {value for value in (requested_mskus or []) if value}
    matches = nested & requested
    if len(matches) == 1:
        return next(iter(matches))
    if len(nested) == 1:
        return next(iter(nested))
    return None


def _query_grain(row: dict[str, Any], msku: str | None, asin: str | None) -> str:
    """Use the source row's actual grain; do not trust requested dimensions."""

    row_type = (_text(row.get("row_type")) or "").lower()
    if msku or "msku" in row_type:
        return "msku_day"
    if asin or "asin" in row_type:
        return "asin_day"
    if "sku" in row_type:
        return "sku_day"
    return "unknown_day"


class LingXingSalesSync:
    TOOL_ID = "query_product_performance_asin_lists"
    PAGE_SIZE = 1000

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
        start_date: date,
        end_date: date,
        mskus: list[str] | None = None,
        currency_code: str = "USD",
        page_size: int = PAGE_SIZE,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise LingXingSyncError("销量同步开始日期不能晚于结束日期")
        if page_size not in {20, 50, 100, 200, 500, 1000}:
            raise LingXingSyncError("产品表现接口页大小不在允许范围内")

        session = self.session_factory()
        started_at = self.clock()
        request_base = {
            "length": page_size,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "date_type": "purchase",
            "date_view_type": "day",
            "date_view_order_type": 1,
            "date_sort_type": "asc",
            "search_field": "msku",
            "search_value": mskus or [],
            "summary_field": "msku",
            "summary_field_level1": "msku",
            "turn_on_summary": 1,
            "sort_field": "volume",
            "sort_type": "desc",
            "currency_code": currency_code,
            "query_order_profit": False,
        }
        batch = LingXingSyncBatch(
            tool_id=self.TOOL_ID,
            request_params=request_base,
            started_at=started_at,
        )
        session.add(batch)
        session.commit()

        msku_cache = {item.msku: item for item in session.scalars(select(LingXingMskuProduct))}
        listing_cache = {
            (item.msku_product_id, item.asin): item
            for item in session.scalars(select(LingXingListing))
        }
        rows_written = 0
        pages = 0
        seen_keys: set[str] = set()
        try:
            offset = 0
            while True:
                request = {**request_base, "offset": offset}
                payload = await self.client.call_tool(self.TOOL_ID, request)
                error = _payload_error(payload)
                rows, reported_total = extract_list_payload(payload)
                if error and not rows:
                    raise LingXingSyncError(error)
                if not rows:
                    break

                for row in rows:
                    sales_date = _as_date(_first(row, "rdate", "sales_date", "date"), start_date)
                    msku = _resolve_msku(row, mskus)
                    asin = _text(_first(row, "asin", "amazon_asin"))
                    sid = _positive_int(_first(row, "sid", "store_id"))
                    mid = _positive_int(_first(row, "mid", "market_id"))
                    grain = _query_grain(row, msku, asin)
                    row_key = _payload_hash(
                        {"date": sales_date.isoformat(), "msku": msku, "asin": asin, "sid": sid, "mid": mid, "row": row}
                    )
                    if row_key in seen_keys:
                        continue
                    seen_keys.add(row_key)
                    msku_product = msku_cache.get(msku) if msku else None
                    listing = listing_cache.get((msku_product.id, asin)) if msku_product and asin else None
                    fingerprint = _payload_hash(request)
                    existing = session.scalar(
                        select(LingXingSalesDaily).where(
                            LingXingSalesDaily.sales_date == sales_date,
                            LingXingSalesDaily.query_fingerprint == fingerprint,
                            LingXingSalesDaily.source_row_key == row_key,
                        )
                    )
                    values = {
                        "msku_product_id": msku_product.id if msku_product else None,
                        "listing_id": listing.id if listing else None,
                        "currency_code": _text(row.get("currency_code")) or currency_code,
                        "query_grain": grain,
                        "query_fingerprint": fingerprint,
                        "source_row_key": row_key,
                        "volume": _decimal(_first(row, "volume", "sales_volume", "quantity")),
                        "sales_amount": _decimal(_first(row, "amount", "sales_amount", "salesAmount")),
                        "order_items": _decimal(_first(row, "order_items", "order_num", "order_items_num")),
                        "refund_quantity": _decimal(_first(row, "return_count", "refund_count", "refund_goods_count")),
                        "raw_payload": dict(row),
                        "sync_batch_id": batch.id,
                        "fetched_at": started_at,
                    }
                    if existing is None:
                        session.add(LingXingSalesDaily(id=uuid.uuid4(), sales_date=sales_date, **values))
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
                            fetched_at=started_at,
                        )
                    )
                    rows_written += 1

                pages += 1
                batch.page_count = pages
                batch.row_count = rows_written
                trace_id = _text(payload.get("traceId")) if isinstance(payload, dict) else None
                if trace_id and trace_id not in (batch.trace_ids or []):
                    batch.trace_ids = [*(batch.trace_ids or []), trace_id]
                session.commit()
                offset += page_size
                if len(rows) < page_size or (reported_total is not None and offset >= reported_total):
                    break

            batch.status = "succeeded"
            batch.finished_at = self.clock()
            session.commit()
            return {
                "batch_id": str(batch.id),
                "pages": pages,
                "rows": rows_written,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
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
