from datetime import date

from app.workflows.lingxing_sales_sync import _as_date, _first, _query_grain, _walk_dicts


def test_sales_date_parser_uses_date_prefix_and_fallback():
    assert _as_date("2026-09-01T12:30:00+00:00", date(2026, 1, 1)) == date(2026, 9, 1)
    assert _as_date("", date(2026, 1, 1)) == date(2026, 1, 1)


def test_sales_helpers_walk_nested_rows_and_aliases():
    nested = {"data": {"list": [{"seller_sku": "MSKU-1", "volume": 3}]}}
    records = list(_walk_dicts(nested))
    assert any(_first(item, "msku", "seller_sku") == "MSKU-1" for item in records)


def test_query_grain_uses_actual_row_identity():
    assert _query_grain({"row_type": "msku_summary"}, "X", None) == "msku_day"
    assert _query_grain({"row_type": "asin_summary"}, None, "A") == "asin_day"
    assert _query_grain({"row_type": "asin_summary"}, None, None) == "asin_day"
