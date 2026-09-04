"""V0.9 deterministic carton-by-carton loading simulator.

This module deliberately does not use the V0.8 EMS/beam state.  A search
state is an executable history of individual cartons.  Every proposed carton
must be able to enter from the high-X door, in one fixed orientation, before
it may become part of a solution.

The model intentionally omits people, fork-lifts, turning clearance and lift
space.  During the straight X insertion an external carrier is assumed.  Once
the carton is released at its final coordinate, however, its bottom must be
fully supported by the floor or cargo that was loaded earlier.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import permutations, product
from math import factorial
import hashlib
import json
import os
import time
from typing import Iterable

from ..models.block import Block
from ..models.placement import Placement
from ..models.solution import OptimizationResult, SolutionMetrics
from .orientation import orientations
from .quantity_optimizer import (
    auto_fill_quantity_upper_bound,
    legal_max_quantity,
    quantity_is_valid,
    validate_quantity_plan,
)


V09_SCOPE = "v0.9-deterministic-carton-replay-door-sweep-full-support"
_INDEX_CELL_MM = 500


@dataclass
class SimulationState:
    """Only valid, already executable cartons are kept in a state."""

    placements: list[Placement] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    volume: float = 0.0
    weight: float = 0.0
    spatial: dict[tuple[int, int, int], list[Placement]] = field(default_factory=dict)
    tops: dict[int, list[Placement]] = field(default_factory=dict)
    indexed_count: int = 0

    def copy(self) -> "SimulationState":
        return SimulationState(
            placements=list(self.placements),
            counts=dict(self.counts),
            volume=self.volume,
            weight=self.weight,
        )


@dataclass(frozen=True)
class CartonCandidate:
    orientation: int
    x: int
    y: int
    z: int
    length: int
    width: int
    height: int
    expands_frontier: bool
    frontier_growth: int


@dataclass
class SimulationResult:
    state: SimulationState | None
    order: tuple[str, ...]
    reason: str = ""
    candidate_checks: int = 0


@dataclass
class CandidatePool:
    """Incremental contact candidates for one SKU during its contiguous run.

    A coordinate is created once from an exposed face.  Invalid coordinates
    are discarded; when a new carton supplies missing support, that carton
    generates the same contact coordinate again.  This keeps construction
    carton-level while avoiding a full re-scan of every old carton per step.
    """

    item: object
    container: object
    coordinates: dict[int, set[tuple[int, int, int]]] = field(default_factory=dict)

    def __post_init__(self):
        self.coordinates = {orientation: {(0, 0, 0)} for orientation, _ in orientations(self.item)}

    def add_anchor(self, carton: Placement) -> None:
        gap = _clearance_y(self.container)
        for orientation, (length, width, height) in orientations(self.item):
            coordinates = self.coordinates.setdefault(orientation, set())
            x_values = (carton.x, carton.x + carton.length - length)
            y_values = (carton.y, carton.y + carton.width - width)
            for x in x_values:
                for y in y_values:
                    coordinates.add((x, y, carton.z + carton.height))
            for y in (carton.y + carton.width + gap, carton.y - width - gap):
                for x in x_values:
                    for z in (0, carton.z, carton.z + carton.height - height):
                        coordinates.add((x, y, z))
            for x in (carton.x - length, carton.x + carton.length):
                for y in y_values:
                    for z in (0, carton.z, carton.z + carton.height - height):
                        coordinates.add((x, y, z))

    def seed(self, placements: Iterable[Placement]) -> None:
        for carton in placements:
            self.add_anchor(carton)

    def ordered(self, state: SimulationState) -> list[CartonCandidate]:
        frontier = _frontier(state.placements)
        candidates = []
        for orientation, (length, width, height) in orientations(self.item):
            for x, y, z in self.coordinates.get(orientation, ()):
                growth = max(0, x + length - frontier)
                candidates.append(CartonCandidate(
                    orientation=orientation, x=x, y=y, z=z,
                    length=length, width=width, height=height,
                    expands_frontier=growth > 0, frontier_growth=growth,
                ))
        candidates.sort(key=_candidate_rank)
        return candidates

    def discard(self, candidate: CartonCandidate) -> None:
        self.coordinates.get(candidate.orientation, set()).discard((candidate.x, candidate.y, candidate.z))


def _clearance_y(container) -> int:
    """V0.9 interprets the configured physical gap as lateral (Y) only."""
    return max(0, int(getattr(container, "clearance_mm_int", 0)))


def _index_keys(rect, clearance_y: int = 0) -> Iterable[tuple[int, int, int]]:
    """Small broad-phase grid used only to avoid repeated all-carton scans."""
    x1, x2 = rect.x, rect.x + rect.length - 1
    y1, y2 = rect.y, rect.y + rect.width + clearance_y - 1
    z1, z2 = rect.z, rect.z + rect.height - 1
    if x2 < x1 or y2 < y1 or z2 < z1:
        return ()
    return product(
        range(x1 // _INDEX_CELL_MM, x2 // _INDEX_CELL_MM + 1),
        range(y1 // _INDEX_CELL_MM, y2 // _INDEX_CELL_MM + 1),
        range(z1 // _INDEX_CELL_MM, z2 // _INDEX_CELL_MM + 1),
    )


def _ensure_index(state: SimulationState, container) -> None:
    if state.indexed_count == len(state.placements):
        return
    state.spatial.clear()
    state.tops.clear()
    clearance_y = _clearance_y(container)
    for carton in state.placements:
        for key in _index_keys(carton, clearance_y):
            state.spatial.setdefault(key, []).append(carton)
        state.tops.setdefault(carton.z + carton.height, []).append(carton)
    state.indexed_count = len(state.placements)


def _index_append(state: SimulationState, carton: Placement, container) -> None:
    _ensure_index(state, container)
    for key in _index_keys(carton, _clearance_y(container)):
        state.spatial.setdefault(key, []).append(carton)
    state.tops.setdefault(carton.z + carton.height, []).append(carton)
    state.indexed_count = len(state.placements)


def _nearby(state: SimulationState, rect, container) -> Iterable[Placement]:
    _ensure_index(state, container)
    seen: set[int] = set()
    for key in _index_keys(rect, _clearance_y(container)):
        for carton in state.spatial.get(key, ()):
            identity = id(carton)
            if identity not in seen:
                seen.add(identity)
                yield carton


def _within(candidate: CartonCandidate, container) -> bool:
    length, width, height = container.dimensions_mm
    return (
        candidate.x >= 0
        and candidate.y >= 0
        and candidate.z >= 0
        and candidate.x + candidate.length <= length
        and candidate.y + candidate.width <= width
        and candidate.z + candidate.height <= height
    )


def _overlaps(a, b, clearance_y: int) -> bool:
    """Strict volume overlap; only side-by-side Y gaps are enforced."""
    return (
        a.x < b.x + b.length
        and a.x + a.length > b.x
        and a.y < b.y + b.width + clearance_y
        and a.y + a.width + clearance_y > b.y
        and a.z < b.z + b.height
        and a.z + a.height > b.z
    )


def _door_accepts(width: int, height: int, container) -> bool:
    if container.door_width is None or container.door_height is None:
        return True
    # The configured 5mm gap applies between cartons, not between a carton and
    # the fixed steel door opening.
    return width <= round(container.door_width * 10) and height <= round(container.door_height * 10)


def _swept_path_clear(candidate: CartonCandidate | Placement, placed: Iterable[Placement], container) -> bool:
    """Check the fixed-orientation, straight X sweep from the high-X door."""
    container_length = container.dimensions_mm[0]
    corridor_start = candidate.x + candidate.length
    if corridor_start >= container_length:
        return True
    corridor = type("Corridor", (), {
        "x": corridor_start,
        "y": candidate.y,
        "z": candidate.z,
        "length": container_length - corridor_start,
        "width": candidate.width,
        "height": candidate.height,
    })()
    clearance_y = _clearance_y(container)
    return not any(_overlaps(corridor, carton, clearance_y) for carton in placed)


def _rectangle_union_area(rectangles: list[tuple[int, int, int, int]]) -> int:
    """Exact union area for X/Y support rectangles."""
    if not rectangles:
        return 0
    xs = sorted({coordinate for left, right, _, _ in rectangles for coordinate in (left, right)})
    area = 0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (bottom, top)
            for x1, x2, bottom, top in rectangles
            if x1 <= left and x2 >= right and bottom < top
        )
        covered = 0
        end = None
        for bottom, top in intervals:
            if end is None:
                end = top
                start = bottom
            elif bottom > end:
                covered += end - start
                start, end = bottom, top
            else:
                end = max(end, top)
        if end is not None:
            covered += end - start
        area += (right - left) * covered
    return area


def _direct_supporters(candidate: CartonCandidate | Placement, placed: Iterable[Placement]) -> list[tuple[int, Placement, int]]:
    """Return earlier cartons touching the candidate's bottom, with contact area."""
    supporters = []
    if candidate.z == 0:
        return supporters
    for index, carton in enumerate(placed):
        if carton.z + carton.height != candidate.z:
            continue
        x1, x2 = max(candidate.x, carton.x), min(candidate.x + candidate.length, carton.x + carton.length)
        y1, y2 = max(candidate.y, carton.y), min(candidate.y + candidate.width, carton.y + carton.width)
        if x1 < x2 and y1 < y2:
            supporters.append((index, carton, (x2 - x1) * (y2 - y1)))
    return supporters


def _fully_supported(candidate: CartonCandidate | Placement, placed: list[Placement]) -> bool:
    if candidate.z == 0:
        return True
    rectangles = []
    for _, carton, _ in _direct_supporters(candidate, placed):
        rectangles.append((
            max(candidate.x, carton.x),
            min(candidate.x + candidate.length, carton.x + carton.length),
            max(candidate.y, carton.y),
            min(candidate.y + candidate.width, carton.y + carton.width),
        ))
    return _rectangle_union_area(rectangles) == candidate.length * candidate.width


def _fully_supported_in_state(candidate: CartonCandidate, state: SimulationState, container) -> bool:
    if candidate.z == 0:
        return True
    _ensure_index(state, container)
    rectangles = []
    for carton in state.tops.get(candidate.z, ()):
        x1, x2 = max(candidate.x, carton.x), min(candidate.x + candidate.length, carton.x + carton.length)
        y1, y2 = max(candidate.y, carton.y), min(candidate.y + candidate.width, carton.y + carton.width)
        if x1 < x2 and y1 < y2:
            rectangles.append((x1, x2, y1, y2))
    return _rectangle_union_area(rectangles) == candidate.length * candidate.width


def _state_path_clear(candidate: CartonCandidate, state: SimulationState, container) -> bool:
    container_length = container.dimensions_mm[0]
    corridor_start = candidate.x + candidate.length
    if corridor_start >= container_length:
        return True
    corridor = type("Corridor", (), {
        "x": corridor_start,
        "y": candidate.y,
        "z": candidate.z,
        "length": container_length - corridor_start,
        "width": candidate.width,
        "height": candidate.height,
    })()
    return not any(_overlaps(corridor, carton, _clearance_y(container)) for carton in _nearby(state, corridor, container))


def _stack_and_load_valid(placements: list[Placement], item_by_sku: dict) -> tuple[bool, bool, bool]:
    """Validate optional stack/load metadata without relaxing geometric support."""
    direct: list[list[tuple[int, int]]] = [[] for _ in placements]
    depths = [1 for _ in placements]
    for index, carton in enumerate(placements):
        if carton.z == 0:
            continue
        supports = _direct_supporters(carton, placements[:index])
        direct[index] = [(support_index, area) for support_index, _, area in supports]
        if direct[index]:
            depths[index] = 1 + max(depths[support_index] for support_index, _ in direct[index])

    stack_ok = True
    for index, carton in enumerate(placements):
        limit = item_by_sku[carton.sku].stack_limit
        if limit is not None and depths[index] > limit:
            stack_ok = False
            break

    top_load = [0.0 for _ in placements]
    for index in sorted(range(len(placements)), key=lambda value: placements[value].z, reverse=True):
        supports = direct[index]
        if not supports:
            continue
        transfer = placements[index].weight_kg + top_load[index]
        total_area = sum(area for _, area in supports)
        for support_index, area in supports:
            top_load[support_index] += transfer * area / total_area

    top_ok = True
    fragile_ok = True
    for index, carton in enumerate(placements):
        item = item_by_sku[carton.sku]
        if item.max_top_load_kg is not None and top_load[index] > item.max_top_load_kg + 1e-9:
            top_ok = False
        if item.fragile and top_load[index] > 1e-9:
            fragile_ok = False
    return stack_ok, top_ok, fragile_ok


def _frontier(placements: list[Placement]) -> int:
    return max((carton.x + carton.length for carton in placements), default=0)


def _local_coordinates(state: SimulationState, length: int, width: int, height: int, container) -> set[tuple[int, int, int]]:
    """Finite, deterministic contact coordinates for a single carton.

    These are carton corners on a floor, a top face, a lateral face, or an
    X face.  The search never creates arbitrary floating coordinates.
    """
    gap = _clearance_y(container)
    coordinates: set[tuple[int, int, int]] = {(0, 0, 0)}
    for carton in state.placements:
        x_values = (carton.x, carton.x + carton.length - length)
        y_values = (carton.y, carton.y + carton.width - width)

        # Top face: all four aligned corners.  Support validation below
        # decides whether the entire bottom is actually covered.
        for x in x_values:
            for y in y_values:
                coordinates.add((x, y, carton.z + carton.height))

        # Both lateral faces, using floor or an existing matching level.
        for y in (carton.y + carton.width + gap, carton.y - width - gap):
            for x in x_values:
                for z in (0, carton.z, carton.z + carton.height - height):
                    coordinates.add((x, y, z))

        # Head/door faces.  These provide the next X column only after all
        # reachable Y/Z gaps have been considered by the rank function.
        for x in (carton.x - length, carton.x + carton.length):
            for y in y_values:
                for z in (0, carton.z, carton.z + carton.height - height):
                    coordinates.add((x, y, z))
    return coordinates


def _candidate_rank(candidate: CartonCandidate) -> tuple[int, int, int, int, int, int]:
    """Hard gap-first classification, then cross-section before X extension."""
    return (
        int(candidate.expands_frontier),
        candidate.frontier_growth,
        candidate.x,
        candidate.z,
        candidate.y,
        candidate.orientation,
    )


def _candidate_is_valid(state: SimulationState, item, candidate: CartonCandidate, container,
                        item_by_sku: dict, enforce_load_rules: bool) -> bool:
    if not _within(candidate, container) or not _door_accepts(candidate.width, candidate.height, container):
        return False
    if state.weight + item.carton_weight_kg > container.max_payload + 1e-9:
        return False
    if container.operational_mode == "hard_limit" and state.volume + item.volume_m3 > container.operational_target_cbm + 1e-9:
        return False
    if any(_overlaps(candidate, carton, _clearance_y(container)) for carton in _nearby(state, candidate, container)):
        return False
    if not _state_path_clear(candidate, state, container):
        return False
    if not _fully_supported_in_state(candidate, state, container):
        return False
    if not enforce_load_rules:
        return True
    probe = Placement(
        box_id="PROBE", sku=item.sku, factory=item.factory,
        x=candidate.x, y=candidate.y, z=candidate.z,
        length=candidate.length, width=candidate.width, height=candidate.height,
        orientation=candidate.orientation, weight_kg=item.carton_weight_kg,
        loading_stage=item.effective_loading_stage,
    )
    stack_ok, top_ok, fragile_ok = _stack_and_load_valid(state.placements + [probe], item_by_sku)
    return stack_ok and top_ok and fragile_ok


def _candidate_options(state: SimulationState, item, container, *, exhaustive: bool = False) -> list[CartonCandidate]:
    """Generate and canonically sort possible contact coordinates.

    Geometry is deliberately not checked here.  Construction can stop at the
    first valid option, while independent probes can check the complete list.
    """
    frontier = _frontier(state.placements)
    candidates: list[CartonCandidate] = []
    for orientation, (length, width, height) in orientations(item):
        coordinates = _local_coordinates(state, length, width, height, container)
        if exhaustive:
            # Independent single-carton probe: any legal axis-aligned carton
            # can be shifted until it contacts a boundary/carton face.  Add
            # the finite cross product of those contact coordinates.
            gap = _clearance_y(container)
            xs = {0, container.dimensions_mm[0] - length}
            ys = {0, container.dimensions_mm[1] - width}
            zs = {0, container.dimensions_mm[2] - height}
            for carton in state.placements:
                xs.update((carton.x, carton.x + carton.length, carton.x - length))
                ys.update((carton.y, carton.y + carton.width + gap, carton.y - width - gap))
                zs.update((carton.z, carton.z + carton.height))
            # This probe is only used after a completed load.  It exits on
            # the first legal carton, so a large coordinate set is acceptable
            # and does not affect construction order.
            coordinates.update(product(xs, ys, zs))
        for x, y, z in sorted(coordinates):
            growth = max(0, x + length - frontier)
            candidate = CartonCandidate(
                orientation=orientation, x=x, y=y, z=z,
                length=length, width=width, height=height,
                expands_frontier=growth > 0,
                frontier_growth=growth,
            )
            candidates.append(candidate)
    candidates.sort(key=_candidate_rank)
    unique = {}
    for candidate in candidates:
        unique.setdefault((candidate.orientation, candidate.x, candidate.y, candidate.z), candidate)
    return list(unique.values())


def _valid_candidates(state: SimulationState, item, container, item_by_sku: dict,
                      *, exhaustive: bool = False) -> list[CartonCandidate]:
    """Return every legal candidate; used only by tests and independent probes."""
    enforce_load_rules = any(
        candidate.stack_limit is not None or candidate.max_top_load_kg is not None or candidate.fragile
        for candidate in item_by_sku.values()
    )
    return [
        candidate for candidate in _candidate_options(state, item, container, exhaustive=exhaustive)
        if _candidate_is_valid(state, item, candidate, container, item_by_sku, enforce_load_rules)
    ]


def _first_valid_candidate(state: SimulationState, item, container, item_by_sku: dict) -> tuple[CartonCandidate | None, int]:
    """Find the first valid candidate in the hard gap-first ordering."""
    enforce_load_rules = any(
        candidate.stack_limit is not None or candidate.max_top_load_kg is not None or candidate.fragile
        for candidate in item_by_sku.values()
    )
    checks = 0
    for candidate in _candidate_options(state, item, container):
        checks += 1
        if _candidate_is_valid(state, item, candidate, container, item_by_sku, enforce_load_rules):
            return candidate, checks
    return None, checks


def _first_valid_from_pool(state: SimulationState, pool: CandidatePool, container,
                           item_by_sku: dict) -> tuple[CartonCandidate | None, int]:
    """Take the first currently valid candidate from an incremental pool."""
    enforce_load_rules = any(
        candidate.stack_limit is not None or candidate.max_top_load_kg is not None or candidate.fragile
        for candidate in item_by_sku.values()
    )
    checks = 0
    for candidate in pool.ordered(state):
        checks += 1
        if _candidate_is_valid(state, pool.item, candidate, container, item_by_sku, enforce_load_rules):
            return candidate, checks
        # Adding cargo cannot repair collision, path, boundary or door errors.
        # A missing-support coordinate is regenerated by the carton that later
        # completes that support surface, so discarding is safe here as well.
        pool.discard(candidate)
    return None, checks


def _append(state: SimulationState, item, candidate: CartonCandidate, container) -> SimulationState:
    """Construction is single-path per SKU order, so mutate its valid state."""
    number = len(state.placements) + 1
    carton = Placement(
        box_id=f"{item.sku}-P{number:04d}", sku=item.sku, factory=item.factory,
        x=candidate.x, y=candidate.y, z=candidate.z,
        length=candidate.length, width=candidate.width, height=candidate.height,
        orientation=candidate.orientation, weight_kg=item.carton_weight_kg,
        loading_stage=item.effective_loading_stage,
    )
    state.placements.append(carton)
    _index_append(state, carton, container)
    state.counts[item.sku] = state.counts.get(item.sku, 0) + 1
    state.volume += item.volume_m3
    state.weight += item.carton_weight_kg
    return state


def _simulate_order(items: list, order: tuple[str, ...], container) -> SimulationResult:
    """Run one declared SKU order without interleaving SKUs."""
    item_by_sku = {item.sku: item for item in items}
    state = SimulationState(counts={item.sku: 0 for item in items})
    candidate_checks = 0
    for sku in order:
        item = item_by_sku[sku]
        target = legal_max_quantity(item, container) if item.is_auto_fill else item.min_quantity
        pool = CandidatePool(item, container)
        pool.seed(state.placements)
        while state.counts[item.sku] < target:
            candidate, checks = _first_valid_from_pool(state, pool, container, item_by_sku)
            candidate_checks += checks
            if candidate is None:
                if item.is_auto_fill:
                    # Preserve its quantity step while retaining a valid
                    # prefix of the already replayable sequence.
                    while state.counts[item.sku] % item.quantity_step:
                        for index in range(len(state.placements) - 1, -1, -1):
                            if state.placements[index].sku == item.sku:
                                removed = state.placements.pop(index)
                                state.counts[item.sku] -= 1
                                state.volume -= item.volume_m3
                                state.weight -= removed.weight_kg
                                break
                    break
                return SimulationResult(None, order, f"{sku} 无可达合法位置", candidate_checks)
            # Candidates are already ordered with the hard gap-first rule.
            state = _append(state, item, candidate, container)
            pool.add_anchor(state.placements[-1])
    return SimulationResult(state, order, candidate_checks=candidate_checks)


def _stage_order_combinations(items: list, max_combinations: int) -> list[tuple[str, ...]]:
    """Enumerate all same-stage SKU orders; AUTO is always the final SKU."""
    by_stage: dict[int, list] = defaultdict(list)
    for item in items:
        by_stage[item.effective_loading_stage].append(item)
    per_stage = []
    combination_count = 1
    for stage in sorted(by_stage):
        stage_items = by_stage[stage]
        fixed = [item for item in stage_items if not item.is_auto_fill]
        auto = [item for item in stage_items if item.is_auto_fill]
        fixed.sort(key=lambda item: items.index(item))
        combination_count *= factorial(len(fixed))
        if combination_count > max_combinations:
            raise ValueError(
                f"V0.9 需要枚举 {combination_count} 种SKU顺序，超过当前安全上限 {max_combinations}；"
                "请减少同阶段SKU数量或提高顺序枚举上限。"
            )
        alternatives = [tuple(item.sku for item in option) + tuple(item.sku for item in auto)
                        for option in permutations(fixed)]
        per_stage.append(alternatives or [tuple(item.sku for item in auto)])
    combinations = [tuple(sku for stage in choice for sku in stage) for choice in product(*per_stage)]
    return combinations


def _order_ranks(order: tuple[str, ...], item_by_sku: dict) -> dict[str, tuple[int, int]]:
    ranks: dict[str, tuple[int, int]] = {}
    counters: dict[int, int] = defaultdict(int)
    for sku in order:
        stage = item_by_sku[sku].effective_loading_stage
        ranks[sku] = (stage, counters[stage])
        counters[stage] += 1
    return ranks


def replay_validate_v09(placements: list[Placement], items: list, container,
                        order: tuple[str, ...]) -> tuple[dict[str, bool], dict[str, int]]:
    """Independent V0.9 replay; it does not call construction helpers."""
    item_by_sku = {item.sku: item for item in items}
    ranks = _order_ranks(order, item_by_sku)
    loaded: list[Placement] = []
    quantity = {item.sku: 0 for item in items}
    last_rank = (-1, -1)
    no_overlap = within_container = supported = door_valid = orientation_valid = True
    accessibility_valid = sequence_valid = True

    for carton in placements:
        item = item_by_sku.get(carton.sku)
        if item is None:
            sequence_valid = orientation_valid = False
            continue
        rank = ranks.get(carton.sku, (-1, -1))
        if rank < last_rank:
            sequence_valid = False
        last_rank = max(last_rank, rank)
        legal = dict(orientations(item))
        if legal.get(carton.orientation) != (carton.length, carton.width, carton.height):
            orientation_valid = False
        candidate = CartonCandidate(
            orientation=carton.orientation, x=carton.x, y=carton.y, z=carton.z,
            length=carton.length, width=carton.width, height=carton.height,
            expands_frontier=False, frontier_growth=0,
        )
        if not _within(candidate, container):
            within_container = False
        if not _door_accepts(carton.width, carton.height, container):
            door_valid = False
        if any(_overlaps(candidate, previous, _clearance_y(container)) for previous in loaded):
            no_overlap = False
        if not _swept_path_clear(candidate, loaded, container):
            accessibility_valid = False
        if not _fully_supported(candidate, loaded):
            supported = False
        loaded.append(carton)
        quantity[carton.sku] += 1

    quantity_valid = quantity_is_valid(quantity, items, container)
    stack_valid, top_load_valid, fragile_valid = _stack_and_load_valid(loaded, item_by_sku)
    validation = {
        "no_overlap": no_overlap,
        "within_container": within_container,
        "weight_ok": sum(carton.weight_kg for carton in loaded) <= container.max_payload + 1e-9,
        "supported": supported,
        "legal_orientations": orientation_valid,
        "quantity_constraints": quantity_valid,
        "door_valid": door_valid,
        "stack_limit_valid": stack_valid,
        "top_load_valid": top_load_valid,
        "fragile_valid": fragile_valid,
        "factory_sequence_valid": sequence_valid,
        "accessibility_valid": accessibility_valid,
        "sequence_valid": sequence_valid and accessibility_valid,
    }
    validation["valid"] = all(validation.values())
    return validation, quantity


def _group_rows(placements: list[Placement], items: list, container) -> tuple[list[Placement], list[Block]]:
    """Compress consecutive X or Y carton rows for presentation only."""
    item_by_sku = {item.sku: item for item in items}
    assigned: list[Placement] = []
    blocks: list[Block] = []
    index = 0
    block_number = 1
    y_gap = _clearance_y(container)
    while index < len(placements):
        first = placements[index]
        row = [first]
        cursor = index + 1
        axis = None
        expected_x = first.x + first.length
        expected_y = first.y + first.width + y_gap
        while cursor < len(placements):
            candidate = placements[cursor]
            common = (
                candidate.sku == first.sku
                and candidate.orientation == first.orientation
                and candidate.z == first.z
                and candidate.width == first.width
                and candidate.height == first.height
                and candidate.length == first.length
            )
            if axis is None and common:
                if candidate.x == first.x and candidate.y == expected_y:
                    axis = "y"
                elif candidate.y == first.y and candidate.x == expected_x:
                    axis = "x"
            if (
                not common
                or (axis == "y" and (candidate.x != first.x or candidate.y != expected_y))
                or (axis == "x" and (candidate.y != first.y or candidate.x != expected_x))
                or axis is None
            ):
                break
            row.append(candidate)
            expected_x += candidate.length
            expected_y += candidate.width + y_gap
            cursor += 1
        block_id = f"{first.sku}-B{block_number:03d}"
        item = item_by_sku[first.sku]
        blocks.append(Block(
            block_id=block_id, sku=first.sku,
            nx=len(row) if axis == "x" else 1,
            ny=len(row) if axis == "y" else 1,
            nz=1, box_count=len(row),
            x=first.x, y=first.y, z=first.z,
            length=first.length * len(row) if axis == "x" else first.length,
            width=(first.width * len(row) + y_gap * (len(row) - 1)) if axis == "y" else first.width,
            height=first.height,
            orientation=first.orientation,
            weight_kg=sum(carton.weight_kg for carton in row),
            volume_m3=len(row) * item.volume_m3,
            loading_stage=first.loading_stage,
        ))
        assigned.extend(carton.model_copy(update={"block_id": block_id}) for carton in row)
        index = cursor
        block_number += 1
    return assigned, blocks


def _has_independent_auto_move(state: SimulationState, auto_item, container, item_by_sku: dict) -> bool:
    """Independent contact-coordinate single-carton maximality probe."""
    return bool(_valid_candidates(state, auto_item, container, item_by_sku, exhaustive=True))


def _audit(container, items: list, options: dict, orders: list[tuple[str, ...]],
           selected: SimulationResult, all_results: list[SimulationResult]) -> dict:
    snapshot = {
        "container": {
            "dimensions_mm": container.dimensions_mm,
            "clearance_y_mm": _clearance_y(container),
            "door_at_x_mm": container.dimensions_mm[0],
        },
        "items": [
            {
                "sku": item.sku,
                "dimensions_mm": item.dimensions_mm,
                "min_quantity": item.min_quantity,
                "max_quantity": item.max_quantity,
                "loading_stage": item.effective_loading_stage,
            }
            for item in items
        ],
        "options": options,
    }
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "algorithm": V09_SCOPE,
        "build_version": os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA") or "unknown",
        "input_fingerprint": fingerprint,
        "clearance_rule": "Y-only; X-touch and Z-stacking contact allowed",
        "insertion_rule": "fixed orientation, high-X door to low-X straight sweep, external carrier during motion",
        "support_rule": "final carton bottom must be 100% covered by earlier floor/carton tops",
        "enumerated_order_count": len(orders),
        "completed_order_count": sum(result.state is not None for result in all_results),
        "selected_order": list(selected.order),
        "selected_candidate_checks": selected.candidate_checks,
        "failed_orders": [
            {"order": list(result.order), "reason": result.reason}
            for result in all_results if result.state is None
        ],
        "effective_options": options,
    }


def optimize_container_v09(container, items: list, mode: str = "UNIFIED_STAGE_MAX", options: dict | None = None) -> OptimizationResult:
    """Run V0.9's order-enumerated deterministic carton simulation."""
    started = time.perf_counter()
    options = dict(options or {})
    validate_quantity_plan(items)
    if len({item.sku for item in items}) != len(items):
        raise ValueError("SKU identifiers must be unique")
    max_orders = max(1, int(options.get("max_order_combinations", 720)))
    orders = _stage_order_combinations(items, max_orders)
    results = [_simulate_order(items, order, container) for order in orders]
    valid = [result for result in results if result.state is not None]
    if not valid:
        details = next((result.reason for result in results if result.reason), "没有完成固定数量的可执行顺序")
        raise ValueError(f"V0.9 未找到可执行装载方案：{details}")

    auto_item = next((item for item in items if item.is_auto_fill), None)
    def score(result: SimulationResult) -> tuple[int, float, int, int]:
        assert result.state is not None
        auto_count = result.state.counts.get(auto_item.sku, 0) if auto_item else 0
        # Same fixed quantities have equal volume.  Compare actual downstream
        # fill first, then prefer a shorter occupied X frontier and a simpler
        # carton history.  This is a deterministic heuristic, not a proof.
        return (
            auto_count,
            result.state.volume,
            -_frontier(result.state.placements),
            -len(result.state.placements),
        )
    selected = max(valid, key=score)
    assert selected.state is not None

    validation, quantities = replay_validate_v09(selected.state.placements, items, container, selected.order)
    if not validation["valid"]:
        # This should be unreachable.  Keep the protection so a construction
        # bug can never become a green result in the UI.
        raise ValueError("V0.9 独立逐箱回放失败，已拒绝返回该方案")
    placements, blocks = _group_rows(selected.state.placements, items, container)
    item_by_sku = {item.sku: item for item in items}
    # Do not claim local maximality unless the caller explicitly requests the
    # expensive independent single-carton proof.  A normal V0.9 result is
    # still fully executable; it simply makes no optimality assertion.
    locally_maximal = False
    if auto_item is not None and bool(options.get("prove_local_maximal", False)):
        locally_maximal = not _has_independent_auto_move(selected.state, auto_item, container, item_by_sku)
    validation["locally_maximal"] = locally_maximal

    loaded_cbm = sum(quantities[item.sku] * item.volume_m3 for item in items)
    upper = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm
    auto_upper = auto_fill_quantity_upper_bound(items, container)
    auto_count = quantities.get(auto_item.sku, 0) if auto_item else None
    audit = _audit(container, items, {
        "max_order_combinations": max_orders,
        "construction": "deterministic gap-first carton simulation",
        "prove_local_maximal": bool(options.get("prove_local_maximal", False)),
    }, orders, selected, results)
    return OptimizationResult(
        solution_id="V09-SOLUTION-1",
        solution_name="V0.9 可执行逐箱装载",
        mode=mode,
        mix_policy="FIXED_ORDER_PERMUTATION_LAST_STAGE_AUTO",
        clearance_mm=getattr(container, "clearance_mm", 0.0),
        solution_status="BEST_FOUND",
        locally_maximal=locally_maximal,
        loaded_cbm=round(loaded_cbm, 6),
        physical_utilization=loaded_cbm / container.physical_cbm,
        operational_utilization=loaded_cbm / container.operational_target_cbm,
        total_weight_kg=round(sum(carton.weight_kg for carton in placements), 3),
        loaded_boxes=len(placements),
        sku_quantities=quantities,
        blocks=blocks,
        placements=placements,
        loading_sequence=[{
            "step": index,
            "block_id": block.block_id,
            "sku": block.sku,
            "box_count": block.box_count,
            "loading_stage": block.loading_stage,
        } for index, block in enumerate(blocks, 1)],
        metrics=SolutionMetrics(
            balance_score=0.0,
            fragmentation_score=max(0.0, 1.0 - loaded_cbm / max(upper, 1e-9)),
            loading_complexity=min(1.0, len(blocks) / max(1, len(placements))),
        ),
        upper_bound_cbm=round(upper, 6),
        upper_bound_proven=False,
        optimality_gap_percent=None,
        optimization_scope=V09_SCOPE,
        auto_fill_upper_quantity=auto_upper,
        auto_fill_gap_boxes=(max(0, auto_upper - auto_count) if auto_upper is not None and auto_count is not None else None),
        portfolio_candidates=len(valid),
        audit=audit,
        validation=validation,
        solve_time_seconds=round(time.perf_counter() - started, 4),
        initial_seed_cbm=round(loaded_cbm, 6),
        search_improvement_cbm=0.0,
        alternatives=[{
            "sku_order": list(result.order),
            "loaded_boxes": len(result.state.placements),
            "auto_boxes": result.state.counts.get(auto_item.sku, 0) if auto_item and result.state else 0,
            "loaded_cbm": round(result.state.volume, 6) if result.state else 0.0,
        } for result in sorted(valid, key=score, reverse=True)[:8]],
    )
