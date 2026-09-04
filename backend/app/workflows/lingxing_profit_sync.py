"""Synchronize LingXing order-profit report rows into local facts."""

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
    LingXingProfitFact,
    LingXingRawRecord,
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


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)


def _nested_unique(row: dict[str, Any], key: str, container: str) -> str | None:
    values = {
        _text(item.get(key))
        for item in row.get(container, [])
        if isinstance(item, dict) and _text(item.get(key))
    }
    return next(iter(values)) if len(values) == 1 else None


class LingXingProfitSync:
    TOOL_ID = "query_order_profit_list"
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
        start_date: date,
        end_date: date,
        mskus: list[str] | None = None,
        currency_code: str = "USD",
        page_size: int = PAGE_SIZE,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise LingXingSyncError("利润同步开始日期不能晚于结束日期")
        if page_size not in {20, 50, 100, 200, 500}:
            raise LingXingSyncError("利润接口页大小不在允许范围内")

        session = self.session_factory()
        started_at = self.clock()
        request_base = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency_type": currency_code,
            "summary_field": "msku",
            "turn_on_summary": "1",
            "sort_type": "desc",
            "length": str(page_size),
            "offset": "0",
            "source_service": "mcp",
            "external_service_mark": 1,
            "search_field": "seller_sku",
            "search_value": mskus or [],
            "search_type": 0,
            "date_summary_type": 1,
            "service_type": 1,
            "query_order_gross_first": False,
        }
        batch = LingXingSyncBatch(tool_id=self.TOOL_ID, request_params=request_base, started_at=started_at)
        session.add(batch)
        session.commit()

        msku_cache = {item.msku: item for item in session.scalars(select(LingXingMskuProduct))}
        listing_cache = {(item.msku_product_id, item.asin): item for item in session.scalars(select(LingXingListing))}
        rows_written = 0
        pages = 0
        seen_keys: set[str] = set()
        try:
            offset = 0
            while True:
                request = {**request_base, "offset": str(offset)}
                payload = await self.client.call_tool(self.TOOL_ID, request)
                error = _payload_error(payload)
                rows, reported_total = extract_list_payload(payload)
                if error and not rows:
                    raise LingXingSyncError(error)
                if not rows:
                    break

                for row in rows:
                    msku = _text(_first(row, "msku", "seller_sku", "sellerSku")) or _nested_unique(
                        row, "seller_sku", "price_list"
                    )
                    asin = _text(_first(row, "asin", "amazon_asin")) or _nested_unique(row, "asin", "asins")
                    sid = _positive_int(_first(row, "sid", "store_id"))
                    if sid is None and isinstance(row.get("sids"), list) and len(row["sids"]) == 1:
                        sid = _positive_int(row["sids"][0])
                    row_key = _payload_hash({"start": start_date.isoformat(), "end": end_date.isoformat(), "row": row})
                    if row_key in seen_keys:
                        continue
                    seen_keys.add(row_key)
                    msku_product = msku_cache.get(msku) if msku else None
                    listing = listing_cache.get((msku_product.id, asin)) if msku_product and asin else None
                    fingerprint = _payload_hash(request)
                    existing = session.scalar(
                        select(LingXingProfitFact).where(
                            LingXingProfitFact.period_start == start_date,
                            LingXingProfitFact.period_end == end_date,
                            LingXingProfitFact.query_fingerprint == fingerprint,
                            LingXingProfitFact.source_row_key == row_key,
                        )
                    )
                    values = {
                        "msku_product_id": msku_product.id if msku_product else None,
                        "listing_id": listing.id if listing else None,
                        "currency_code": _text(row.get("currency_code")) or currency_code,
                        "summary_field": "msku",
                        "query_fingerprint": fingerprint,
                        "source_row_key": row_key,
                        "volume": _decimal(_first(row, "volume", "sales_volume", "quantity")),
                        "sales_amount": _decimal(_first(row, "amount", "sales_amount")),
                        "gross_profit": _decimal(_first(row, "gross_profit")),
                        "net_amount": _decimal(_first(row, "net_amount")),
                        "total_costs": _decimal(_first(row, "total_costs")),
                        "ad_cost": _decimal(_first(row, "ads_sp_cost", "ad_cost")),
                        "refund_amount": _decimal(_first(row, "refund_amount", "return_amount")),
                        "raw_payload": dict(row),
                        "sync_batch_id": batch.id,
                        "fetched_at": started_at,
                    }
                    if existing is None:
                        session.add(
                            LingXingProfitFact(
                                id=uuid.uuid4(),
                                period_start=start_date,
                                period_end=end_date,
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
                            fetched_at=started_at,
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
            return {"batch_id": str(batch.id), "pages": pages, "rows": rows_written}
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
