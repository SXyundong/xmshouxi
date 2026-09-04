import pytest

from app.container_loading.models.container import Container
from app.container_loading.models.item import Item
from app.container_loading.solver.beam_search import (
    Rect3D, SearchState, _moves, _positions, _previous_rectangles_for_move,
    _stage_x_bounds, beam_pack_solutions, has_legal_single_box_move,
)
from app.container_loading.solver.maximal_spaces import EmptySpace, spaces_after_blocks
from app.container_loading.solver.optimizer import optimize_container
from app.container_loading.solver.quantity_optimizer import validate_quantity_plan
from app.container_loading.solver.quantity_optimizer import auto_fill_quantity_upper_bound
from app.container_loading.solver.stage_portfolio import _select_with_cp_sat


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


def test_ordered_stage_search_finishes_the_selected_sku_before_the_next_one():
    container = Container(container_length=60, container_width=30, container_height=30)
    first = _item("A", minimum=1, maximum=1, stage=1)
    second = _item("B", minimum=1, maximum=1, stage=1)
    states = beam_pack_solutions(
        [first, second], {"A": 1, "B": 1}, container, [],
        beam_width=4, max_block_placements=2, min_support_ratio=1.0,
        stage_sku_orders={1: ("B", "A")},
    )

    assert states
    assert [block["sku"] for block, _ in states[0].blocks[:2]] == ["B", "A"]


def test_later_sku_generates_positions_on_its_active_predecessor_frontier():
    container = Container(container_length=50, container_width=30, container_height=30)
    previous = _item("A", minimum=1, maximum=1, stage=1)
    current = _item("B", minimum=1, maximum=1, stage=2)
    historical = _item("OLD", minimum=1, maximum=1, stage=1)
    cube = {"length": 10, "width": 10, "height": 10, "sku": "A"}
    old_cube = {**cube, "sku": "OLD"}
    state = SearchState(
        blocks=[(cube, (20, 0, 0)), (old_cube, (0, 20, 0))],
        counts={"A": 1, "B": 0, "OLD": 1},
        empty_spaces=spaces_after_blocks(container, [(cube, (20, 0, 0)), (old_cube, (0, 20, 0))]),
        sku_rank_by_sku={"A": 0, "OLD": 1, "B": 0},
        predecessor_by_sku={"A": None, "OLD": "A", "B": "A"},
        active_frontier_only=True,
        stage_index=1,
    )

    moves = _moves(
        state, [current], {"A": 1, "B": 1, "OLD": 1}, container, 1.0, 128,
        realistic=True, all_items=[previous, historical, current], exhaustive=True,
    )
    positions = {position for _, position, _, _ in moves}

    # The predecessor's exposed side is explicitly generated as a candidate,
    # ahead of relying on a coincidental EMS corner.
    assert (20, 10, 0) in positions


def test_same_stage_auto_keeps_its_declared_rank_in_path_validation():
    container = Container(container_length=50, container_width=30, container_height=30)
    fixed = _item("FIXED", minimum=1, maximum=1, stage=3)
    auto = _item("AUTO", stage=3)
    fixed_block = {"sku": "FIXED", "length": 10, "width": 10, "height": 10}
    state = SearchState(
        blocks=[(fixed_block, (20, 0, 0))],
        sku_rank_by_sku={"FIXED": 0, "AUTO": 1},
    )

    previous = _previous_rectangles_for_move(state, auto, (0, 0, 0), [fixed, auto])

    # AUTO is last by SKU rank even when it occupies a deeper X coordinate;
    # the fixed carton must therefore block AUTO's door sweep.
    assert previous == [Rect3D(20, 0, 0, 10, 10, 10)]


def test_independent_single_box_probe_reports_a_full_container_as_maximal():
    container = Container(container_length=10, container_width=10, container_height=10)
    fixed = _item("FIXED", minimum=1, maximum=1)
    auto = _item("AUTO")
    block = {"sku": "FIXED", "length": 10, "width": 10, "height": 10}
    state = SearchState(
        blocks=[(block, (0, 0, 0))], counts={"FIXED": 1, "AUTO": 0},
        empty_spaces=spaces_after_blocks(container, [(block, (0, 0, 0))]),
    )

    assert not has_legal_single_box_move(
        state, auto, {"FIXED": 1, "AUTO": 1}, container, 1.0,
        all_items=[fixed, auto],
    )


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


def test_fixed_layout_uses_cross_section_before_long_axial_wall():
    items = [
        Item(sku="A", carton_length_cm=60, carton_width_cm=41.5, carton_height_cm=24,
             carton_weight_kg=1, min_quantity=200, max_quantity=200, loading_stage=1),
        Item(sku="B", carton_length_cm=97, carton_width_cm=31, carton_height_cm=18,
             carton_weight_kg=1, min_quantity=100, max_quantity=100, loading_stage=2),
        Item(sku="C", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
             carton_weight_kg=1, min_quantity=100, max_quantity=100, loading_stage=2),
    ]

    result = optimize_container(
        Container(), items, "UNIFIED_STAGE_MAX", {
            "time_limit_seconds": 5,
            "beam_width": 24,
            "max_block_placements": 60,
            "solution_limit": 1,
            "lns_rounds": 0,
            "completion_candidate_limit": 1,
            "completion_max_additions": 10,
            "max_blocks_per_sku": 100,
        },
    )

    assert result.sku_quantities == {"A": 200, "B": 100, "C": 100}
    assert result.validation["valid"] is True
    a_blocks = [block for block in result.blocks if block.sku == "A"]
    assert a_blocks and max(block.length for block in a_blocks) <= 3000


def test_stage_portfolio_reports_an_honest_auto_upper_bound():
    fixed = _item("A", minimum=8, maximum=8, stage=1)
    auto = _item("B", stage=2)
    result = optimize_container(
        Container(container_length=80, container_width=30, container_height=30, clearance_mm=5),
        [fixed, auto],
        "UNIFIED_STAGE_MAX",
        {
            "time_limit_seconds": 4,
            "beam_width": 20,
            "max_block_placements": 36,
            "solution_limit": 1,
            "max_blocks_per_sku": 80,
            "fixed_max_blocks_per_sku": 4,
        },
    )

    assert result.validation["valid"] is True
    assert result.solution_status in {"BEST_FOUND", "PORTFOLIO_OPTIMAL"}
    assert result.optimization_scope == "reachable-frontier-hard-auto-floor-ordered-sku-search"
    assert result.upper_bound_proven is False
    assert result.auto_fill_upper_quantity is not None
    assert result.auto_fill_gap_boxes is not None


def test_auto_upper_bound_uses_residual_container_capacity():
    items = [
        Item(sku="A", carton_length_cm=60, carton_width_cm=41.5, carton_height_cm=24,
             carton_weight_kg=9.55, min_quantity=200, max_quantity=200, loading_stage=1),
        Item(sku="B", carton_length_cm=97, carton_width_cm=31, carton_height_cm=18,
             carton_weight_kg=10.45, min_quantity=100, max_quantity=100, loading_stage=2),
        Item(sku="C", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
             carton_weight_kg=16.2, min_quantity=150, max_quantity=150, loading_stage=2),
        Item(sku="D", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
             carton_weight_kg=16.2, min_quantity=0, max_quantity=None, loading_stage=3),
    ]

    assert auto_fill_quantity_upper_bound(items, Container(clearance_mm=5)) == 569


def test_portfolio_selection_maximizes_last_stage_auto_before_compactness():
    fixed = _item("A", minimum=1, maximum=1, stage=1)
    auto = _item("B", stage=2)
    compact_lower_fill = SearchState(
        counts={"A": 1, "B": 5},
        blocks=[({"sku": "A", "length": 10}, (0, 0, 0)), ({"sku": "B", "length": 10}, (10, 0, 0))],
    )
    wider_higher_fill = SearchState(
        counts={"A": 1, "B": 6},
        blocks=[({"sku": "A", "length": 100}, (0, 0, 0)), ({"sku": "B", "length": 100}, (100, 0, 0))],
    )

    selected, proven = _select_with_cp_sat([compact_lower_fill, wider_higher_fill], [fixed, auto])

    assert proven is True
    assert selected[0] is wider_higher_fill


def test_realistic_5mm_stage_mosaic_keeps_top_and_side_fill():
    items = [
        Item(sku="70046", carton_length_cm=60, carton_width_cm=41.5, carton_height_cm=24,
             carton_weight_kg=9.55, min_quantity=200, max_quantity=200, loading_stage=1),
        Item(sku="70047", carton_length_cm=97, carton_width_cm=31, carton_height_cm=18,
             carton_weight_kg=10.45, min_quantity=100, max_quantity=100, loading_stage=2),
        Item(sku="70051-A", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
             carton_weight_kg=16.2, min_quantity=150, max_quantity=150, loading_stage=2),
        Item(sku="70051-D", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
             carton_weight_kg=16.2, min_quantity=0, max_quantity=None, loading_stage=3),
    ]
    result = optimize_container(
        Container(clearance_mm=5), items, "UNIFIED_STAGE_MAX", {
            "time_limit_seconds": 10,
            "beam_width": 32,
            "max_block_placements": 72,
            "solution_limit": 1,
            "stage_portfolio_limit": 4,
            "fixed_max_blocks_per_sku": 6,
        },
    )

    assert result.validation["valid"] is True
    assert result.sku_quantities["70046"] == 200
    assert result.sku_quantities["70047"] == 100
    assert result.sku_quantities["70051-A"] == 150
    # The dedicated X-band regression below verifies the actual top/side
    # candidate.  This timed integration fixture only requires that AUTO is
    # opened after the fixed stage and produces a valid fill.
    assert result.sku_quantities["70051-D"] > 0


def test_exhaustive_contact_positions_include_configured_clearance():
    space = EmptySpace(0, 0, 2230, 10000, 2352, 460)
    block = {"length": 880, "width": 320, "height": 290}
    occupied = [Rect3D(5960, 1625, 2230, 880, 320, 290)]

    normal = _positions(space, block, occupied, False, clearance_mm=5)
    exhaustive = _positions(space, block, occupied, True, clearance_mm=5)

    assert (6845, 1625, 2230) not in normal
    assert (6845, 1625, 2230) in exhaustive
    assert (6840, 1625, 2230) not in exhaustive


def test_auto_fill_can_be_inserted_before_future_door_side_cargo():
    """A deeper carton must not be blocked by cargo loaded later near the door."""
    container = Container(clearance_mm=5)
    support = Item(
        sku="B", carton_length_cm=97, carton_width_cm=31, carton_height_cm=18,
        carton_weight_kg=10.45, min_quantity=100, max_quantity=100, loading_stage=1,
    )
    auto = Item(
        sku="D", carton_length_cm=88, carton_width_cm=32, carton_height_cm=29,
        carton_weight_kg=16.2, min_quantity=0, max_quantity=None, loading_stage=1,
    )
    support_block = {
        "sku": "B", "nx": 25, "ny": 2, "nz": 2, "box_count": 100,
        "length": 7870, "width": 365, "height": 1940,
        "unit_length": 320, "unit_width": 290, "unit_height": 880,
        "orientation": 3, "weight_kg": 1045, "volume_m3": 5.413,
    }
    stacked_block = {
        "sku": "D", "nx": 5, "ny": 1, "nz": 2, "box_count": 10,
        "length": 4420, "width": 320, "height": 580,
        "unit_length": 880, "unit_width": 320, "unit_height": 290,
        "orientation": 0, "weight_kg": 162, "volume_m3": 0.0,
    }
    future_door_block = {
        "sku": "D", "nx": 1, "ny": 1, "nz": 3, "box_count": 3,
        "length": 290, "width": 320, "height": 2640,
        "unit_length": 290, "unit_width": 320, "unit_height": 880,
        "orientation": 5, "weight_kg": 48.6, "volume_m3": 0.0,
    }
    blocks = [
        (support_block, (2420, 1625, 0)),
        (stacked_block, (2420, 1625, 1940)),
        # This cargo is closer to the door and must be loaded after the
        # candidate at x=6845; it may not block that candidate's aisle.
        (future_door_block, (10295, 1625, 0)),
    ]
    state = SearchState(
        blocks=blocks,
        counts={"B": 100, "D": 13},
        empty_spaces=spaces_after_blocks(container, blocks),
        volume=0.0,
        weight=0.0,
        stage_index=0,
    )

    moves = _moves(
        state, [auto], {"B": 100, "D": 9999}, container, 1.0, 10000,
        realistic=True, filler_only=True, all_items=[support, auto], exhaustive=True,
    )

    assert any(
        position == (6845, 1625, 1940)
        and block["orientation"] == 0
        and block["box_count"] == 1
        for block, position, _, _ in moves
    )


def test_auto_fill_cannot_reopen_an_older_head_side_gap():
    """AUTO starts from its immediate predecessor, not an older stage's head gap."""
    container = Container(container_length=100, container_width=50, container_height=50, clearance_mm=5)
    support = Item(
        sku="A", carton_length_cm=20, carton_width_cm=20, carton_height_cm=20,
        carton_weight_kg=1, min_quantity=1, max_quantity=1, loading_stage=1,
    )
    fixed = Item(
        sku="B", carton_length_cm=20, carton_width_cm=20, carton_height_cm=20,
        carton_weight_kg=1, min_quantity=1, max_quantity=1, loading_stage=3,
    )
    auto = Item(
        sku="C", carton_length_cm=20, carton_width_cm=20, carton_height_cm=20,
        carton_weight_kg=1, min_quantity=0, max_quantity=None, loading_stage=3,
    )
    block = lambda sku: {
        "sku": sku, "nx": 1, "ny": 1, "nz": 1, "box_count": 1,
        "length": 200, "width": 200, "height": 200,
        "unit_length": 200, "unit_width": 200, "unit_height": 200,
        "orientation": 0, "weight_kg": 1, "volume_m3": 0.008,
    }
    blocks = [(block("A"), (0, 0, 0)), (block("B"), (500, 0, 0))]
    state = SearchState(
        blocks=blocks, counts={"A": 1, "B": 1, "C": 0},
        empty_spaces=spaces_after_blocks(container, blocks), volume=0.016, weight=2,
        sku_rank_by_sku={"B": 0, "C": 1}, predecessor_by_sku={"C": "B"},
        active_frontier_only=True,
    )

    assert _stage_x_bounds(state, auto, container, [support, fixed, auto])[0] == 500
    moves = _moves(
        state, [auto], {"A": 1, "B": 1, "C": 99}, container, 1.0, 4096,
        realistic=True, filler_only=True, all_items=[support, fixed, auto], exhaustive=True,
    )

    assert not any(
        candidate["box_count"] == 1 and position == (0, 0, 200)
        for candidate, position, _, _ in moves
    )
    assert any(
        candidate["box_count"] == 1 and position == (500, 0, 200)
        for candidate, position, _, _ in moves
    )
