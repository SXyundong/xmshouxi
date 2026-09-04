"""Read-only quality audit for LingXing dimensions and fact tables."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    LingXingInventorySnapshot,
    LingXingListing,
    LingXingListingCurrent,
    LingXingListingSnapshot,
    LingXingMarket,
    LingXingMskuProduct,
    LingXingProfitFact,
    LingXingRawRecord,
    LingXingSalesDaily,
    LingXingStore,
    LingXingSyncBatch,
)


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _date_range(session: Session, model: Any, column: Any) -> dict[str, str | None]:
    minimum, maximum = session.execute(select(func.min(column), func.max(column))).one()
    return {
        "min": minimum.isoformat() if isinstance(minimum, date) else None,
        "max": maximum.isoformat() if isinstance(maximum, date) else None,
    }


def build_lingxing_quality_report(session: Session) -> dict[str, Any]:
    """Return a compact, JSON-serializable audit without changing the DB."""

    sales_grains = {
        grain: int(count)
        for grain, count in session.execute(
            select(LingXingSalesDaily.query_grain, func.count()).group_by(LingXingSalesDaily.query_grain)
        ).all()
    }
    batches = [
        {
            "tool_id": batch.tool_id,
            "status": batch.status,
            "rows": batch.row_count,
            "pages": batch.page_count,
            "error": batch.error_message,
        }
        for batch in session.scalars(
            select(LingXingSyncBatch).order_by(LingXingSyncBatch.started_at.desc()).limit(20)
        )
    ]
    sales_total = _count(session, LingXingSalesDaily)
    profit_total = _count(session, LingXingProfitFact)
    return {
        "dimensions": {
            "stores": _count(session, LingXingStore),
            "markets": _count(session, LingXingMarket),
            "msku_products": _count(session, LingXingMskuProduct),
            "listings": _count(session, LingXingListing),
            "listing_current": _count(session, LingXingListingCurrent),
            "listing_snapshots": _count(session, LingXingListingSnapshot),
        },
        "facts": {
            "sales_daily": sales_total,
            "sales_unresolved_msku": int(
                session.scalar(
                    select(func.count()).select_from(LingXingSalesDaily).where(
                        LingXingSalesDaily.msku_product_id.is_(None)
                    )
                )
                or 0
            ),
            "sales_unresolved_listing": int(
                session.scalar(
                    select(func.count()).select_from(LingXingSalesDaily).where(LingXingSalesDaily.listing_id.is_(None))
                )
                or 0
            ),
            "sales_grains": sales_grains,
            "sales_date_range": _date_range(session, LingXingSalesDaily, LingXingSalesDaily.sales_date),
            "profit_facts": profit_total,
            "profit_unresolved_msku": int(
                session.scalar(
                    select(func.count()).select_from(LingXingProfitFact).where(
                        LingXingProfitFact.msku_product_id.is_(None)
                    )
                )
                or 0
            ),
            "profit_unresolved_listing": int(
                session.scalar(
                    select(func.count()).select_from(LingXingProfitFact).where(LingXingProfitFact.listing_id.is_(None))
                )
                or 0
            ),
            "profit_period_range": {
                "min": _date_range(session, LingXingProfitFact, LingXingProfitFact.period_start)["min"],
                "max": _date_range(session, LingXingProfitFact, LingXingProfitFact.period_end)["max"],
            },
            "inventory_snapshots": _count(session, LingXingInventorySnapshot),
        },
        "raw_records": _count(session, LingXingRawRecord),
        "recent_batches": batches,
    }
