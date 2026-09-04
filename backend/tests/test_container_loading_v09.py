from app.container_loading.models.container import Container
from app.container_loading.models.item import Item
from app.container_loading.models.placement import Placement
from app.container_loading.solver.optimizer import optimize_container
from app.container_loading.solver.v09 import (
    CartonCandidate,
    SimulationState,
    _candidate_is_valid,
    _valid_candidates,
    replay_validate_v09,
)


def _item(sku, *, minimum=0, maximum=None, stage=1, dimensions=(10, 10, 10)):
    return Item(
        sku=sku,
        carton_length_cm=dimensions[0], carton_width_cm=dimensions[1], carton_height_cm=dimensions[2],
        carton_weight_kg=1,
        min_quantity=minimum,
        max_quantity=maximum,
        loading_stage=stage,
    )


def _placement(sku, x, y, z, length, width, height, *, stage=1):
    return Placement(
        box_id=f"{sku}-{x}-{y}-{z}", sku=sku, x=x, y=y, z=z,
        length=length, width=width, height=height, orientation=0,
        weight_kg=1, loading_stage=stage,
    )


def test_v09_replay_rejects_a_door_wall_before_later_cargo():
    """Regression for the V0.8.2 70052-1 door-wall failure."""
    container = Container(container_length=1203.2, container_width=235.2, container_height=269, clearance_mm=5)
    wall = _placement("WALL", 11562, 0, 0, 470, 2315, 2670, stage=2)
    later = _placement("LATER", 7845, 0, 1575, 3620, 1785, 940, stage=3)
    wall_item = _item("WALL", minimum=1, maximum=1, stage=2, dimensions=(47, 231.5, 267))
    later_item = _item("LATER", minimum=1, maximum=1, stage=3, dimensions=(362, 178.5, 94))

    validation, _ = replay_validate_v09([wall, later], [wall_item, later_item], container, ("WALL", "LATER"))

    assert validation["accessibility_valid"] is False
    assert validation["sequence_valid"] is False
    assert validation["valid"] is False


def test_v09_requires_full_final_bottom_support():
    container = Container(container_length=60, container_width=40, container_height=40)
    lower = _item("LOWER", minimum=1, maximum=1)
    upper = _item("UPPER", minimum=1, maximum=1)
    state = SimulationState(placements=[_placement("LOWER", 0, 0, 0, 100, 100, 100)])
    candidate = CartonCandidate(0, 50, 0, 100, 100, 100, 100, False, 0)

    assert not _candidate_is_valid(state, upper, candidate, container, {"LOWER": lower, "UPPER": upper}, False)


def test_v09_applies_clearance_to_y_not_x():
    container = Container(container_length=60, container_width=40, container_height=40, clearance_mm=5)
    item = _item("A", minimum=1, maximum=1)
    state = SimulationState(placements=[_placement("A", 0, 0, 0, 100, 100, 100)])
    axial_touch = CartonCandidate(0, 100, 0, 0, 100, 100, 100, False, 0)
    lateral_too_close = CartonCandidate(0, 0, 100, 0, 100, 100, 100, False, 0)

    assert _candidate_is_valid(state, item, axial_touch, container, {"A": item}, False)
    assert not _candidate_is_valid(state, item, lateral_too_close, container, {"A": item}, False)


def test_v09_uses_reachable_gap_before_extending_x_and_is_deterministic():
    container = Container(container_length=60, container_width=30, container_height=30)
    first = _item("A", minimum=2, maximum=2, stage=1)
    second = _item("B", minimum=1, maximum=1, stage=2)
    auto = _item("AUTO", stage=2)

    result_one = optimize_container(container, [first, second, auto], "UNIFIED_STAGE_MAX")
    result_two = optimize_container(container, [first, second, auto], "UNIFIED_STAGE_MAX")

    assert result_one.optimization_scope == "v0.9-deterministic-carton-replay-door-sweep-full-support"
    assert result_one.validation["valid"] is True
    assert result_one.sku_quantities == result_two.sku_quantities
    assert [(p.sku, p.x, p.y, p.z, p.orientation) for p in result_one.placements] == [
        (p.sku, p.x, p.y, p.z, p.orientation) for p in result_two.placements
    ]
    # A uses its Y-side gap at X=0 before the simulator is allowed to advance X.
    assert [(p.x, p.y, p.z) for p in result_one.placements[:2]] == [(0, 0, 0), (0, 100, 0)]


def test_v09_candidate_set_contains_lateral_gap_before_axial_extension():
    container = Container(container_length=60, container_width=30, container_height=30)
    item = _item("A", minimum=1, maximum=1)
    state = SimulationState(placements=[_placement("A", 0, 0, 0, 100, 100, 100)])

    candidates = _valid_candidates(state, item, container, {"A": item})

    assert candidates[0].x == 0
    assert candidates[0].y == 100
    assert candidates[0].z == 0
