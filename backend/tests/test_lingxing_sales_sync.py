from datetime import date

from app.workflows.lingxing_sales_sync import _as_date, _first, _query_grain, _resolve_msku, _walk_dicts
from app.workflows.lingxing_profit_sync import _nested_unique
from app.tools.lingxing_tool import _extract_msku


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


def test_resolve_msku_from_nested_price_list_when_asin_summary_has_no_msku():
    row = {
        "row_type": "asin_summary",
        "msku": None,
        "price_list": [
            {"seller_sku": "60001UK01HXD", "volume": "1"},
            {"seller_sku": "60001DE01HXD", "volume": "0"},
        ],
    }
    assert _resolve_msku(row, ["60001UK01HXD"]) == "60001UK01HXD"


def test_profit_nested_identity_only_resolves_unique_value():
    assert _nested_unique({"price_list": [{"seller_sku": "M1"}]}, "seller_sku", "price_list") == "M1"
    assert _nested_unique(
        {"price_list": [{"seller_sku": "M1"}, {"seller_sku": "M2"}]}, "seller_sku", "price_list"
    ) is None


def test_agent_msku_extractor_does_not_treat_dates_as_msku():
    assert _extract_msku("分析 2026-08-01 到 2026-08-02") is None
    assert _extract_msku("分析 MSKU 60005US01HXD 2026-08-02") == "60005US01HXD"
