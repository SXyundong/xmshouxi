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
import time

from .beam_search import SearchState, beam_pack_solutions
from .block_generator import generate_blocks
from .block_generator import _axis_capacity, _vertical_limit
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
    )


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
    pareto = _pareto_fixed_states(
        fixed_states, fixed_items, auto_item, container,
        limit=max(2, min(8, portfolio_limit)),
    )

    if auto_item is None:
        selected, selected_by_cp_sat = _select_with_cp_sat(pareto, items)
        return selected[:max(1, solution_limit * 4)], PortfolioMetadata(len(pareto), len(pareto), selected_by_cp_sat, "pattern-portfolio")

    expanded: list[SearchState] = []
    for index, fixed_state in enumerate(pareto):
        if time.perf_counter() >= deadline:
            break
        # Give every Pareto seed a comparable share of the remaining time so
        # an early, merely compact seed cannot starve a more fillable one.
        seeds_left = len(pareto)-index
        remaining = max(0.0, deadline-time.perf_counter())
        seed_deadline = min(deadline, time.perf_counter()+max(0.5, remaining/max(1, seeds_left)))
        seed = _copy_for_all_items(fixed_state, items, fixed_items)
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
