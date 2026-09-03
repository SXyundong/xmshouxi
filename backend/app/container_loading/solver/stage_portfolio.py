"""Stage-aware candidate portfolio for container loading.

The production problem has two different goals that a single greedy search
cannot represent well: fixed factory cargo must be compact and executable,
while the last-stage SKU should consume as much of the remaining space as
possible.  This module keeps a Pareto portfolio of fixed-stage layouts before
opening the final auto-fill stage.

CP-SAT is deliberately used only for the discrete portfolio selection and the
quantity upper bound.  A selected layout is still expanded and independently
validated carton-by-carton by the existing geometry validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
import time

from .accessibility import swept_path_clear
from .beam_search import (
    Rect3D,
    SearchState,
    _door_accepts_block,
    _placed_rectangles,
    _positions,
    _stage_x_bounds,
    _moves,
    beam_pack_solutions,
)
from .block_generator import generate_blocks
from .block_generator import _axis_capacity, _vertical_limit
from .geometry import overlaps, support_ratio, within
from .maximal_spaces import initial_space, subtract_placement, spaces_after_blocks
from .orientation import orientations
from .quantity_optimizer import legal_max_quantity


@dataclass(frozen=True)
class PortfolioMetadata:
    fixed_candidates: int
    expanded_candidates: int
    selected_by_cp_sat: bool
    scope: str


def _copy_for_all_items(state: SearchState, items: list, fixed_items: list) -> SearchState:
    """Make a fixed-stage state usable by the all-stage beam search."""
    counts = {item.sku: state.counts.get(item.sku, 0) for item in items}
    all_stages = sorted({item.effective_loading_stage for item in items})
    fixed_stages = sorted({item.effective_loading_stage for item in fixed_items})
    last_fixed = fixed_stages[-1] if fixed_stages else all_stages[0]
    return SearchState(
        blocks=list(state.blocks), counts=counts, empty_spaces=list(state.empty_spaces),
        volume=state.volume, weight=state.weight,
        stage_index=all_stages.index(last_fixed),
        sku_rank_by_sku=dict(state.sku_rank_by_sku),
        predecessor_by_sku=dict(state.predecessor_by_sku),
        active_frontier_only=state.active_frontier_only,
    )


def _state_signature(state: SearchState) -> tuple:
    return tuple(
        (block["sku"], position, block["nx"], block["ny"], block["nz"], block["orientation"])
        for block, position in state.blocks
    )


def _exact_block_definitions(item, container, max_candidates: int = 140) -> list[dict]:
    """Return exact fixed-quantity patterns, including narrow cross-section blocks."""
    if item.min_quantity <= 0:
        return []
    blocks = [
        block for block in generate_blocks(item, container, max_candidates)
        if block["box_count"] == item.min_quantity
    ]
    # Keep all exact patterns for normal product sizes, with a stable order
    # that favours a wide cross-section and then a short axial span.
    blocks.sort(key=lambda block: (
        block["width"] * block["height"],
        -block["length"],
        block["width"],
        block["height"],
        block["orientation"],
    ), reverse=True)
    return blocks[:max_candidates]


def _append_exact_block(state: SearchState, item, block: dict, position: tuple[int, int, int], container, all_items) -> SearchState | None:
    """Append one exact fixed block after independent physical checks."""
    x, y, z = position
    occupied = _placed_rectangles(state)
    if not within(x, y, z, block["length"], block["width"], block["height"], container):
        return None
    if not _door_accepts_block(block, item, container):
        return None
    candidate_rect = Rect3D(
        x, y, z, block["length"], block["width"], block["height"],
    )
    if any(overlaps(candidate_rect, existing, getattr(container, "clearance_mm_int", 0))
           for existing in occupied):
        return None
    if support_ratio(x, y, z, block["length"], block["width"], occupied) + 1e-9 < 1.0:
        return None
    if not swept_path_clear(x, y, z, block["length"], block["width"], block["height"], occupied, container):
        return None
    stage_bounds = _stage_x_bounds(state, item, container, all_items)
    if stage_bounds is not None:
        stage_start, frontier = stage_bounds
        clearance = getattr(container, "clearance_mm_int", 0)
        if x < stage_start or x > frontier + clearance:
            return None
    counts = state.counts.copy()
    counts[item.sku] = counts.get(item.sku, 0) + block["box_count"]
    blocks = state.blocks + [(block, position)]
    return SearchState(
        blocks=blocks,
        counts=counts,
        empty_spaces=subtract_placement(
            state.empty_spaces, x, y, z, block["length"], block["width"], block["height"],
            clearance_mm=getattr(container, "clearance_mm_int", 0),
        ),
        volume=state.volume + block["volume_m3"],
        weight=state.weight + block["weight_kg"],
        stage_index=state.stage_index,
    )


def _exact_fixed_stage_patterns(items: list, container, limit: int = 24) -> list[SearchState]:
    """Enumerate compact one-block-per-SKU stage patterns before beam pruning.

    This supplements the normal EMS beam with exact quantity patterns.  It is
    intentionally generic: the dimensions and quantity of each SKU determine
    the blocks; no product-specific coordinates are used.
    """
    fixed_items = [item for item in items if not item.is_auto_fill]
    if not fixed_items:
        return []
    stages = sorted({item.effective_loading_stage for item in fixed_items})
    definitions = {item.sku: _exact_block_definitions(item, container) for item in fixed_items}
    if any(not definitions[item.sku] for item in fixed_items):
        return []
    states = [SearchState(counts={item.sku: 0 for item in fixed_items}, empty_spaces=initial_space(container))]
    def trim_diverse(candidates: list[SearchState], cap: int) -> list[SearchState]:
        """Bound the pattern pool without losing a block-shape family."""
        ranked = sorted(candidates, key=lambda state: (
            state.volume,
            -sum(block["length"] for block, _ in state.blocks),
            -len(state.blocks),
        ), reverse=True)
        selected = []
        seen_families = set()
        stage_by_sku = {
            candidate.sku: candidate.effective_loading_stage
            for candidate in fixed_items
        }

        def has_same_stage_overlap(state: SearchState) -> bool:
            stage_blocks = [
                (block, position)
                for block, position in state.blocks
                if block["sku"] in stage_by_sku
            ]
            for index, (left, left_position) in enumerate(stage_blocks):
                left_stage = stage_by_sku[left["sku"]]
                for right, right_position in stage_blocks[index + 1:]:
                    if stage_by_sku[right["sku"]] != left_stage or left["sku"] == right["sku"]:
                        continue
                    if (left_position[0] < right_position[0] + right["length"] and
                            right_position[0] < left_position[0] + left["length"]):
                        return True
            return False

        # Preserve a bounded number of cross-section mosaics even when their
        # axial span is slightly longer than a zoned layout.  These patterns
        # are exactly the ones that leave useful side/top EMS for auto fill.
        mosaic_candidates = [state for state in ranked if has_same_stage_overlap(state)]
        for state in mosaic_candidates[:max(1, cap // 3)]:
            family = tuple(
                (block["sku"], block["nx"], block["ny"], block["nz"], block["orientation"], position)
                for block, position in state.blocks
            )
            selected.append(state)
            seen_families.add(family)
            if len(selected) >= cap:
                return selected
        for state in ranked:
            family = tuple(
                (block["sku"], block["nx"], block["ny"], block["nz"], block["orientation"], position)
                for block, position in state.blocks
            )
            if family in seen_families:
                continue
            selected.append(state)
            seen_families.add(family)
            if len(selected) >= cap:
                return selected
        for state in ranked:
            if state not in selected:
                selected.append(state)
            if len(selected) >= cap:
                break
        return selected

    for stage in stages:
        group = [item for item in fixed_items if item.effective_loading_stage == stage]
        orders = list(permutations(group)) if len(group) <= 5 else [tuple(group)]
        next_states = []
        for base in states:
            for order in orders:
                partial = [base]
                for item in order:
                    placed = []
                    for state in partial:
                        for block in definitions[item.sku]:
                            # For a fixed stage, evaluate front/side EMS in
                            # loading order first.  This keeps a compact
                            # cross-section mosaic alive before the generic
                            # volume-ranked spaces consume the branch cap.
                            spaces = sorted(state.empty_spaces, key=lambda space: (space.x, space.y, space.z, -space.volume))
                            block_placed = False
                            stage_by_sku = {
                                candidate.sku: candidate.effective_loading_stage
                                for candidate in fixed_items
                            }
                            stage_blocks = [
                                (placed_block, placed_position)
                                for placed_block, placed_position in state.blocks
                                if stage_by_sku.get(placed_block["sku"]) == item.effective_loading_stage
                            ]
                            clearance = getattr(container, "clearance_mm_int", 0)
                            stage_anchors = []
                            if stage_blocks:
                                stage_start = min(position[0] for _, position in stage_blocks)
                                stage_frontier = max(position[0] + placed_block["length"]
                                                     for placed_block, position in stage_blocks)
                                stage_floor = min(position[1] for _, position in stage_blocks)
                                stage_ceiling = max(position[1] + placed_block["width"]
                                                    for placed_block, position in stage_blocks)
                                stage_anchors = [
                                    (stage_start, stage_ceiling + clearance, 0),
                                    (stage_frontier + clearance, stage_floor, 0),
                                ]
                            positions = stage_anchors + [
                                position
                                for space in spaces
                                for position in _positions(space, block, _placed_rectangles(state), exhaustive=False)
                            ]
                            for position in dict.fromkeys(positions):
                                candidate = _append_exact_block(
                                    state, item, block, position, container, fixed_items,
                                )
                                if candidate is not None:
                                    placed.append(candidate)
                                    # One front-most placement per exact
                                    # block shape is enough here.  The later
                                    # Pareto stage retains the resulting shape
                                    # diversity and avoids multiplying
                                    # equivalent translations.
                                    block_placed = True
                                    break
                            if len(placed) >= limit * 4:
                                break
                        if len(placed) >= limit * 4:
                            break
                    unique = {}
                    for candidate in placed:
                        unique.setdefault(_state_signature(candidate), candidate)
                    partial = list(unique.values())
                    if len(partial) > limit * 4:
                        partial = trim_diverse(partial, limit * 4)
                    if not partial:
                        break
                next_states.extend(partial)
        unique = {}
        for state in next_states:
            unique.setdefault(_state_signature(state), state)
        states = list(unique.values())
        if len(states) > limit * 4:
            states = trim_diverse(states, limit * 4)
        if not states:
            return []
    return states[:limit * 4]


def _apply_move(state: SearchState, move, container) -> SearchState:
    block, (x, y, z), _, _ = move
    counts = state.counts.copy()
    counts[block["sku"]] = counts.get(block["sku"], 0) + block["box_count"]
    return SearchState(
        blocks=state.blocks + [(block, (x, y, z))],
        counts=counts,
        empty_spaces=subtract_placement(
            state.empty_spaces, x, y, z, block["length"], block["width"], block["height"],
            clearance_mm=getattr(container, "clearance_mm_int", 0),
        ),
        volume=state.volume + block["volume_m3"],
        weight=state.weight + block["weight_kg"],
        stage_index=state.stage_index,
    )


def _top_fill_seeds(state: SearchState, items: list, auto_item, container, limit: int = 3) -> list[SearchState]:
    """Seed the auto stage with small supported blocks on top of fixed cargo."""
    if auto_item is None:
        return []
    quantity = {item.sku: legal_max_quantity(item, container) for item in items}
    moves = _moves(
        state, [auto_item], quantity, container, 1.0, 4096,
        realistic=True, filler_only=True, all_items=items,
    )
    top_moves = [move for move in moves if move[1][2] > 0]
    top_moves.sort(key=lambda move: (
        move[0]["box_count"],
        move[0]["width"] * move[0]["height"],
        -move[1][0],
    ), reverse=True)
    return [_apply_move(state, move, container) for move in top_moves[:limit]]


def _stage_spans(state: SearchState, items: list) -> tuple[int, int]:
    by_sku = {item.sku: item.effective_loading_stage for item in items}
    spans = []
    for stage in sorted(set(by_sku.values())):
        blocks = [(block, position) for block, position in state.blocks if by_sku[block["sku"]] == stage]
        if blocks:
            spans.append(max(x + block["length"] for block, (x, _, _) in blocks) - min(x for _, (x, _, _) in blocks))
    return sum(spans), max(spans, default=0)


def _fragmentation(state: SearchState, items: list) -> int:
    fixed_skus = {item.sku for item in items if not item.is_auto_fill}
    by_sku = {sku: 0 for sku in fixed_skus}
    for block, _ in state.blocks:
        if block["sku"] in by_sku:
            by_sku[block["sku"]] += 1
    # Squaring makes a plan that scatters a single SKU into many blocks lose
    # against one with the same total number of blocks spread more evenly.
    return sum(count * count for count in by_sku.values())


def _respects_fixed_block_limit(state: SearchState, fixed_items: list, limit: int) -> bool:
    counts = {item.sku: 0 for item in fixed_items}
    for block, _ in state.blocks:
        if block["sku"] in counts:
            counts[block["sku"]] += 1
    return all(count <= limit for count in counts.values())


def _rough_auto_capacity(state: SearchState, auto_item, container) -> int:
    """A comparison signal only; EMS overlap means it is never an upper bound."""
    clearance = getattr(container, "clearance_mm_int", 0)
    capacity = 0
    for space in state.empty_spaces:
        best = 0
        for _, (length, width, height) in orientations(auto_item):
            nx = _axis_capacity(space.length, length, clearance)
            ny = _axis_capacity(space.width, width, clearance)
            nz = _vertical_limit(auto_item, space.height // height)
            best = max(best, nx * ny * nz)
        capacity += best
    return capacity


def _fixed_quality(state: SearchState, fixed_items: list, auto_item, container) -> tuple[int, int, int, int]:
    total_span, maximum_span = _stage_spans(state, fixed_items)
    fragments = _fragmentation(state, fixed_items)
    # Higher residual potential is better, so use its negative in a minimising
    # quality tuple.
    residual = -_rough_auto_capacity(state, auto_item, container) if auto_item else 0
    return total_span, maximum_span, fragments, residual


def _dominates(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))


def _pareto_fixed_states(states: list[SearchState], fixed_items: list, auto_item, container, limit: int) -> list[SearchState]:
    scored = [(state, _fixed_quality(state, fixed_items, auto_item, container)) for state in states]
    frontier = [
        entry for index, entry in enumerate(scored)
        if not any(_dominates(other_score, entry[1]) for other_index, (_, other_score) in enumerate(scored)
                   if other_index != index)
    ]
    # Keep a little diversity even when the formal frontier is large.
    frontier.sort(key=lambda entry: entry[1])
    selected = frontier[:limit]
    if len(selected) < limit:
        seen = {id(state) for state, _ in selected}
        for entry in sorted(scored, key=lambda item: item[1]):
            if id(entry[0]) not in seen:
                selected.append(entry)
                seen.add(id(entry[0]))
            if len(selected) >= limit:
                break
    return [state for state, _ in selected]


def _select_with_cp_sat(states: list[SearchState], items: list) -> tuple[list[SearchState], bool]:
    """Apply the declared lexicographic business objective to the portfolio.

    The CP-SAT problem is intentionally small: each candidate is an already
    geometry-feasible stage pattern.  CP-SAT proves the selection is optimal
    *within this generated portfolio*, not within arbitrary 3D placements.
    """
    if len(states) <= 1:
        return states, False
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return states, False

    auto_item = next((item for item in items if item.is_auto_fill), None)
    qualities = []
    for state in states:
        total_span, maximum_span = _stage_spans(state, items)
        # This is used as a tie-break only after the last-stage capacity has
        # been maximised.  The hard block cap applied before this method is
        # the business guardrail that keeps fixed factory cargo executable.
        qualities.append(total_span * 100_000 + maximum_span * 100 + _fragmentation(state, items))
    auto_counts = [state.counts.get(auto_item.sku, 0) if auto_item else 0 for state in states]

    model = cp_model.CpModel()
    choose = [model.NewBoolVar(f"pattern_{index}") for index in range(len(states))]
    model.AddExactlyOne(choose)
    quality_value = sum(value * variable for value, variable in zip(qualities, choose))
    auto_value = sum(value * variable for value, variable in zip(auto_counts, choose))
    # The business priority is: fixed quantities and stable-stage guardrails
    # first (already guaranteed by the candidate generator), then as many
    # cartons as possible for the last, automatic SKU.  Among equal quantities
    # use the compactest fixed-stage plan.
    model.Maximize(auto_value)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 1.0
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return states, False
    best_auto_count = int(round(solver.ObjectiveValue()))

    model.Add(auto_value == best_auto_count)
    model.Minimize(quality_value)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return states, False
    selected_index = next(index for index, variable in enumerate(choose) if solver.Value(variable))
    # Keep the selected candidate first and expose the remaining portfolio as
    # alternatives in the existing response contract.
    ordered = [states[selected_index]] + [state for index, state in enumerate(states) if index != selected_index]
    return ordered, status == cp_model.OPTIMAL


def staged_portfolio_search(container, items: list, *, beam_width: int, max_block_placements: int,
                            min_support_ratio: float, solution_limit: int, deadline: float,
                            max_blocks_per_sku: int = 140,
                            fixed_max_blocks_per_sku: int = 6,
                            portfolio_limit: int = 6) -> tuple[list[SearchState], PortfolioMetadata]:
    """Search fixed stages first, then expand every Pareto candidate with auto fill."""
    fixed_items = [item for item in items if not item.is_auto_fill]
    auto_item = next((item for item in items if item.is_auto_fill), None)
    all_blocks = [
        block
        for item in items
        for block in generate_blocks(item, container, max_blocks_per_sku)
    ]
    ceilings = {item.sku: legal_max_quantity(item, container) for item in items}

    if not fixed_items:
        initial = SearchState(counts={item.sku: 0 for item in items})
        # The ordinary beam constructor provides initial EMS when initial_states
        # is omitted, so let it create the auto-only search state itself.
        expanded = beam_pack_solutions(
            items, ceilings, container, all_blocks, beam_width, max_block_placements,
            min_support_ratio, None, "UNIFIED_STAGE_MAX", archive_limit=max(16, solution_limit * 8), deadline=deadline,
        )
        selected, selected_by_cp_sat = _select_with_cp_sat(expanded, items)
        return selected[:max(1, solution_limit * 4)], PortfolioMetadata(0, len(expanded), selected_by_cp_sat, "pattern-portfolio")

    fixed_blocks = [block for item in fixed_items for block in generate_blocks(item, container, max_blocks_per_sku)]
    fixed_quantities = {item.sku: legal_max_quantity(item, container) for item in fixed_items}
    # Do not let the fixed-layout search consume the entire job budget.  We
    # need time to evaluate several remaining-space patterns with the auto
    # SKU; that comparison is the purpose of this staged search.
    remaining = max(0.0, deadline-time.perf_counter())
    fixed_deadline = min(deadline, time.perf_counter()+max(0.8, remaining*0.38))
    fixed_states = beam_pack_solutions(
        fixed_items, fixed_quantities, container, fixed_blocks,
        max(beam_width, 36), max_block_placements,
        min_support_ratio, None, "UNIFIED_STAGE_MAX", archive_limit=max(36, portfolio_limit * 10), deadline=fixed_deadline,
    )
    bounded_fixed_states = [
        state for state in fixed_states
        if _respects_fixed_block_limit(state, fixed_items, fixed_max_blocks_per_sku)
    ]
    # Feasibility must always win over an aesthetic limit.  When the carton
    # dimensions make the cap impossible, continue with the unfiltered set.
    if bounded_fixed_states:
        fixed_states = bounded_fixed_states
    # The ordinary beam is still useful for unusual shapes and split blocks,
    # but exact fixed-stage patterns must enter the portfolio before Pareto
    # pruning.  This is where compact B/C mosaics that the beam would discard
    # are preserved for the auto-fill comparison.
    exact_patterns = _exact_fixed_stage_patterns(fixed_items, container, limit=max(4, portfolio_limit * 4))
    fixed_states.extend(
        state for state in exact_patterns
        if _respects_fixed_block_limit(state, fixed_items, fixed_max_blocks_per_sku)
    )
    pareto = _pareto_fixed_states(
        fixed_states, fixed_items, auto_item, container,
        limit=max(2, min(8, portfolio_limit)),
    )

    if auto_item is None:
        selected, selected_by_cp_sat = _select_with_cp_sat(pareto, items)
        return selected[:max(1, solution_limit * 4)], PortfolioMetadata(len(pareto), len(pareto), selected_by_cp_sat, "pattern-portfolio")

    expanded: list[SearchState] = []
    expansion_seeds = []
    for fixed_state in pareto:
        seed = _copy_for_all_items(fixed_state, items, fixed_items)
        expansion_seeds.append(seed)
        # One largest supported top seed per fixed pattern is sufficient to
        # expose the top-space topology; the normal beam then refines it.
        expansion_seeds.extend(_top_fill_seeds(seed, items, auto_item, container, limit=1))

    for index, seed in enumerate(expansion_seeds):
        if time.perf_counter() >= deadline:
            break
        # Give every Pareto seed a comparable share of the remaining time so
        # an early, merely compact seed cannot starve a more fillable one.
        seeds_left = len(expansion_seeds)-index
        remaining = max(0.0, deadline-time.perf_counter())
        seed_deadline = min(deadline, time.perf_counter()+max(0.5, remaining/max(1, seeds_left)))
        expanded.extend(beam_pack_solutions(
            items, ceilings, container, all_blocks,
            max(beam_width, 32), max_block_placements,
            min_support_ratio, [seed], "UNIFIED_STAGE_MAX",
            archive_limit=max(6, solution_limit * 3), deadline=seed_deadline,
        ))
    # The all-stage beam archive includes fixed-only intermediates.  Keep only
    # candidates that actually placed the last-stage SKU when possible.
    with_auto = [state for state in expanded if state.counts.get(auto_item.sku, 0) > 0]
    pool = with_auto or expanded or pareto
    selected, selected_by_cp_sat = _select_with_cp_sat(pool, items)
    return selected[:max(1, solution_limit * 6)], PortfolioMetadata(len(pareto), len(pool), selected_by_cp_sat, "pattern-portfolio")
