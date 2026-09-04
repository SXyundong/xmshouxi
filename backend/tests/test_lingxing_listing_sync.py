from app.db.models import LingXingStore
from app.workflows.lingxing_listing_sync import (
    _country_code,
    _decimal,
    _payload_hash,
    _positive_int,
    extract_list_payload,
)


def test_extract_list_payload_unwraps_gateway_envelope_and_total():
    rows, total = extract_list_payload({"data": {"data": {"list": [{"id": 7}], "total": "12"}}})
    assert rows == [{"id": 7}]
    assert total == 12


def test_extract_list_payload_accepts_direct_list():
    rows, total = extract_list_payload([{"id": 1}, "ignored"])
    assert rows == [{"id": 1}]
    assert total is None


def test_extract_list_payload_accepts_nested_items_used_by_analytics():
    rows, total = extract_list_payload({"data": {"data": {"items": [{"msku": "A"}], "total": 1}}})
    assert rows == [{"msku": "A"}]
    assert total == 1


def test_numeric_helpers_are_tolerant_of_placeholders():
    assert _positive_int("0") is None
    assert _positive_int("12") == 12
    assert _decimal("12.50") == 12.50
    assert _decimal("-") is None


def test_country_mapping_prefers_store_country_and_hash_is_stable():
    store = LingXingStore(sid=1, store_name="US", country_code="us")
    assert _country_code({"marketplace": "德国"}, store) == "US"
    assert _country_code({"marketplace": "德国"}, None) == "DE"
    assert _payload_hash({"b": 2, "a": 1}) == _payload_hash({"a": 1, "b": 2})
