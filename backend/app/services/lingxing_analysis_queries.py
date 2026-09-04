"""Read-only queries over the stable LingXing analysis views."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, Decimal)):
        return value.isoformat() if isinstance(value, date) else str(value)
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in result.mappings()]


def query_sales(
    session: Session,
    start_date: date,
    end_date: date,
    msku: str | None = None,
    asin: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    filters = ["sales_date BETWEEN :start_date AND :end_date"]
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, "limit": limit, "offset": offset}
    if msku:
        filters.append("msku = :msku")
        params["msku"] = msku
    if asin:
        filters.append("asin = :asin")
        params["asin"] = asin
    where = " AND ".join(filters)
    total = session.execute(text(f"SELECT count(*) FROM lingxing_sales_analysis WHERE {where}"), params).scalar() or 0
    rows = session.execute(
        text(
            f"SELECT sales_date, query_grain, msku, asin, currency_code, volume, sales_amount, order_items, refund_quantity "
            f"FROM lingxing_sales_analysis WHERE {where} ORDER BY sales_date DESC, id LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "total": int(total), "rows": _rows(rows)}


def query_profit(
    session: Session,
    start_date: date,
    end_date: date,
    msku: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    filters = ["period_start <= :end_date AND period_end >= :start_date"]
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, "limit": limit, "offset": offset}
    if msku:
        filters.append("msku = :msku")
        params["msku"] = msku
    where = " AND ".join(filters)
    total = session.execute(text(f"SELECT count(*) FROM lingxing_profit_analysis WHERE {where}"), params).scalar() or 0
    rows = session.execute(
        text(
            f"SELECT period_start, period_end, summary_field, msku, asin, currency_code, volume, sales_amount, "
            f"gross_profit, net_amount, total_costs, ad_cost, refund_amount FROM lingxing_profit_analysis "
            f"WHERE {where} ORDER BY period_end DESC, id LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "total": int(total), "rows": _rows(rows)}


def query_inventory(
    session: Session,
    msku: str | None = None,
    asin: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    filters: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if msku:
        filters.append("msku = :msku")
        params["msku"] = msku
    if asin:
        filters.append("asin = :asin")
        params["asin"] = asin
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    total = session.execute(text(f"SELECT count(*) FROM lingxing_inventory_latest {where}"), params).scalar() or 0
    rows = session.execute(
        text(
            "SELECT snapshot_at, msku, asin, fnsku, inventory_source, available_qty, reserved_qty, "
            "inbound_working_qty, inbound_shipped_qty, inbound_receiving_qty, unsellable_qty, store_id, market_id "
            f"FROM lingxing_inventory_latest {where} ORDER BY snapshot_at DESC, msku NULLS LAST LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return {"total": int(total), "rows": _rows(rows)}


def summarize(session: Session, start_date: date, end_date: date, msku: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    msku_filter = ""
    if msku:
        msku_filter = " AND msku = :msku"
        params["msku"] = msku
    sales = session.execute(
        text(
            "SELECT count(*) AS rows, COALESCE(sum(volume), 0) AS volume, COALESCE(sum(sales_amount), 0) AS sales_amount "
            f"FROM lingxing_sales_analysis WHERE sales_date BETWEEN :start_date AND :end_date{msku_filter}"
        ),
        params,
    ).mappings().one()
    profit = session.execute(
        text(
            "SELECT count(*) AS rows, COALESCE(sum(gross_profit), 0) AS gross_profit, "
            "COALESCE(sum(net_amount), 0) AS net_amount FROM lingxing_profit_analysis "
            f"WHERE period_start <= :end_date AND period_end >= :start_date{msku_filter}"
        ),
        params,
    ).mappings().one()
    inventory = session.execute(
        text(
            "SELECT count(*) AS rows, COALESCE(sum(available_qty), 0) AS available_qty, "
            "count(*) FILTER (WHERE available_qty <= 0) AS zero_stock_rows FROM lingxing_inventory_latest "
            f"WHERE 1=1{msku_filter}"
        ),
        params,
    ).mappings().one()
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "msku": msku,
        "sales": {key: _json_value(value) for key, value in sales.items()},
        "profit": {key: _json_value(value) for key, value in profit.items()},
        "inventory": {key: _json_value(value) for key, value in inventory.items()},
    }
