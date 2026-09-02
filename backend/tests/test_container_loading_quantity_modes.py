import pytest

from app.container_loading.models.container import Container
from app.container_loading.models.item import Item
from app.container_loading.solver.optimizer import optimize_container
from app.container_loading.solver.quantity_optimizer import validate_quantity_plan


def _item(sku, *, minimum=0, maximum=None, stage=1):
    return Item(
        sku=sku,
        carton_length_cm=10,
        carton_width_cm=10,
        carton_height_cm=10,
        carton_weight_kg=1,
        min_quantity=minimum,
        max_quantity=maximum,
        loading_stage=stage,
    )


def test_fixed_and_last_stage_auto_plan_is_valid():
    fixed = _item("A", minimum=2, maximum=2, stage=1)
    auto = _item("B", stage=2)

    validate_quantity_plan([fixed, auto])


def test_quantity_range_is_rejected():
    with pytest.raises(ValueError, match="不支持数量范围"):
        _item("A", minimum=1, maximum=2)


def test_auto_fill_must_be_the_last_stage_and_unique():
    fixed = _item("A", minimum=1, maximum=1, stage=2)
    earlier_auto = _item("B", stage=1)
    with pytest.raises(ValueError, match="最后一个装载顺序"):
        validate_quantity_plan([fixed, earlier_auto])

    later_auto = _item("C", stage=2)
    with pytest.raises(ValueError, match="只能设置一个自动填充商品"):
        validate_quantity_plan([fixed, later_auto, _item("D", stage=2)])


def test_staged_search_preserves_large_fixed_quantities():
    items = [
        _item("A", minimum=10, maximum=10, stage=1),
        _item("B", minimum=10, maximum=10, stage=1),
        _item("C", minimum=10, maximum=10, stage=2),
    ]
    for item, dimensions in zip(items, ((9, 14, 11), (13, 9, 12), (11, 11, 11))):
        item.carton_length_cm, item.carton_width_cm, item.carton_height_cm = dimensions

    result = optimize_container(
        Container(container_length=100, container_width=30, container_height=30),
        items,
        "UNIFIED_STAGE_MAX",
        {
            "time_limit_seconds": 5,
            "beam_width": 32,
            "max_block_placements": 72,
            "solution_limit": 1,
            "lns_rounds": 0,
            "completion_candidate_limit": 24,
            "completion_max_additions": 100,
            "max_blocks_per_sku": 140,
        },
    )

    assert result.sku_quantities == {"A": 10, "B": 10, "C": 10}
    assert result.validation["valid"] is True
