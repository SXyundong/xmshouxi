from app.workflows.inbound_placement_fee import calculate_inbound_placement_fee


def test_small_standard_uses_actual_weight_and_upper_bound_fee():
    result = calculate_inbound_placement_fee(15, 10, 1, 200)
    assert result is not None
    assert result.segment == "小号标准尺寸"
    assert result.actual_weight_lbs == 0.441
    assert result.single_point_fee == 0.32
    assert result.partial_split_fee is None


def test_large_standard_uses_shipping_weight():
    result = calculate_inbound_placement_fee(30, 20, 10, 500)
    assert result is not None
    assert result.segment == "大号标准尺寸"
    assert result.volumetric_weight_lbs > result.actual_weight_lbs
    assert result.single_point_fee == 0.60


def test_small_bulky_calculates_both_fees():
    result = calculate_inbound_placement_fee(70.5, 8.3, 4, 2570)
    assert result is not None
    assert result.segment == "小号大件"
    assert result.single_point_fee == 2.40
    assert result.partial_split_fee == 1.75


def test_oversize_is_not_priced():
    result = calculate_inbound_placement_fee(150, 30, 12.5, 7550)
    assert result is not None
    assert result.segment == "超大件（0 至 50 磅）"
    assert result.single_point_fee is None
    assert result.partial_split_fee is None
