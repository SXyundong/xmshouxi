"""V0.8.1 reachable-frontier ordered-SKU staged search.

Each factory stage enumerates its SKU orders.  A SKU is fully placed before
the next SKU in that order opens; only the final AUTO SKU can continue without
a requested quantity.  A new SKU explicitly scans the active predecessor band
(side/top gaps before advancing towards the door); all remaining candidates
still require the same geometry and straight-X insertion checks.
"""

from __future__ import annotations

from itertools import product, permutations
import time

from .beam_search import SearchState, beam_pack_solutions, complete_state
from .maximal_spaces import initial_space
from .orientation import orientations
from .quantity_optimizer import legal_max_quantity
from .stage_portfolio import PortfolioMetadata


def _signature(state: SearchState) -> tuple:
    return tuple(
        (block["sku"], position, block["nx"], block["ny"], block["nz"], block["orientation"])
        for block, position in state.blocks
    )


def _stage_orders(items: list, maximum_per_stage: int = 24) -> list[dict[int, tuple[str, ...]]]:
    """Return deterministic SKU orders, with AUTO always last in its stage."""
    by_stage: dict[int, list] = {}
    for item in items:
        by_stage.setdefault(item.effective_loading_stage, []).append(item)
    choices = []
    for stage in sorted(by_stage):
        fixed = sorted((item for item in by_stage[stage] if not item.is_auto_fill), key=lambda item: item.sku)
        auto = [item for item in by_stage[stage] if item.is_auto_fill]
        orders = list(permutations(fixed)) if len(fixed) <= 4 else [tuple(fixed)]
        choices.append([
            (stage, tuple(item.sku for item in order + tuple(auto)))
            for order in orders[:maximum_per_stage]
        ])
    plans = []
    for combined in product(*choices):
        plans.append(dict(combined))
        if len(plans) >= maximum_per_stage:
            break
    return plans or [{}]


def _order_metadata(
    order: dict[int, tuple[str, ...]],
) -> tuple[dict[str, int], dict[str, str | tuple[str, ...] | None]]:
    """Turn one selected SKU order into the search and validation contract.

    The rank is local to a factory stage.  The first SKU of factory N may use
    the active X band left by factory N-1; later SKUs in that same factory
    are chained to their immediately preceding SKU.
    """
    ranks: dict[str, int] = {}
    predecessors: dict[str, str | tuple[str, ...] | None] = {}
    previous_stage: tuple[str, ...] = ()
    for stage in sorted(order):
        previous_sku: str | None = None
        for rank, sku in enumerate(order[stage]):
            ranks[sku] = rank
            # A new factory can use any part of the active band belonging to the
            # factory loaded immediately before it.  Within one factory the
            # hand-off is stricter: B grows from A, then C grows from B.
            predecessors[sku] = previous_sku if previous_sku is not None else (previous_stage or None)
            previous_sku = sku
        previous_stage = order[stage]
    return ranks, predecessors


def _future_space_score(state: SearchState, next_items: list) -> tuple[int, int, int]:
    """Score empty space for the next SKU before compactness/volume ties.

    Width-height area is deliberately weighted above axial length: a layout
    that leaves several supported top/side lanes is more useful to the next
    factory than one that leaves one deceptively large, narrow X corridor.
    """
    area = 0
    supported_volume = 0
    for space in state.empty_spaces:
        fits = []
        for item in next_items:
            for _, (length, width, height) in orientations(item):
                if length <= space.length and width <= space.width and height <= space.height:
                    fits.append((width * height, length * width * height))
        if fits:
            best_area, best_volume = max(fits)
            area += best_area
            supported_volume += best_volume
    return area, supported_volume, -len(state.empty_spaces)


def _stage_span(state: SearchState, stage: int, by_sku: dict) -> int:
    ranges = [
        (position[0], position[0] + block["length"])
        for block, position in state.blocks
        if by_sku.get(block["sku"], None) == stage
    ]
    return max((end for _, end in ranges), default=0) - min((start for start, _ in ranges), default=0)


def _search_one_order(container, items, ceilings, order, *, beam_width, max_block_placements,
                      min_support_ratio, solution_limit, deadline) -> list[SearchState]:
    """Complete one declared order stage by stage before opening AUTO.

    Searching each completed factory stage separately keeps its diverse valid
    layouts alive for the following factory.  A monolithic beam otherwise
    spends most of the budget repeatedly expanding already-complete earlier
    stages, which is especially harmful for a three-factory load.
    """
    ranks, predecessors = _order_metadata(order)
    states = [SearchState(
        counts={item.sku: 0 for item in items}, empty_spaces=initial_space(container),
        sku_rank_by_sku=ranks, predecessor_by_sku=predecessors, active_frontier_only=True,
    )]
    # Keep a real layout portfolio for the next factory.  Four nearly
    # identical states are not enough when one arrangement blocks a later
    # carton while another leaves a usable top lane.
    state_limit = max(8, solution_limit * 8)
    by_sku = {item.sku: item for item in items}
    for stage in sorted(order):
        if deadline is not None and time.perf_counter() >= deadline:
            return []
        stage_items = [by_sku[sku] for sku in order[stage] if sku in by_sku]
        states = beam_pack_solutions(
            stage_items, ceilings, container, [], max(8, beam_width), max_block_placements,
            min_support_ratio, states, "UNIFIED_STAGE_MAX",
            archive_limit=max(16, state_limit * 3), deadline=deadline,
            stage_sku_orders={stage: order[stage]},
            sku_rank_by_sku=ranks, predecessor_by_sku=predecessors,
            active_frontier_only=True, all_items_for_moves=items,
        )
        if not states:
            return []
        next_stage = sorted(order)[sorted(order).index(stage) + 1:] if stage != sorted(order)[-1] else []
        if next_stage:
            next_items = [by_sku[sku] for sku in order[next_stage[0]] if sku in by_sku]
            states.sort(key=lambda state: (
                -_stage_span(state, stage, {item.sku: item.effective_loading_stage for item in items}),
                _future_space_score(state, next_items),
                state.volume,
                -len(state.blocks),
            ), reverse=True)
        states = states[:state_limit]
    return states


def stack_scan_search(container, items: list, *, beam_width: int, max_block_placements: int,
                      min_support_ratio: float, solution_limit: int, deadline: float | None,
                      max_blocks_per_sku: int = 140, fixed_max_blocks_per_sku: int = 6,
                      portfolio_limit: int = 6) -> tuple[list[SearchState], PortfolioMetadata]:
    """Evaluate deterministic same-stage SKU orders and then AUTO fill."""
    auto_item = next((item for item in items if item.is_auto_fill), None)
    ceilings = {item.sku: legal_max_quantity(item, container) for item in items}
    plans = _stage_orders(items)
    planned_order_count = len(plans)
    expanded: list[SearchState] = []
    for index, order in enumerate(plans):
        if deadline is not None and time.perf_counter() >= deadline:
            break
        # Establish a deterministic baseline first.  It prevents a complex
        # order with many permutations from spending every small API budget
        # on incomplete candidates; remaining time still compares the other
        # orders deterministically.
        order_deadline = None
        if deadline is not None:
            remaining_orders = max(1, len(plans)-index)
            remaining = max(0.0, deadline-time.perf_counter())
            share = remaining * 0.65 if index == 0 and len(plans) > 1 else remaining / remaining_orders
            order_deadline = min(deadline, time.perf_counter() + max(0.05, share))
        states = _search_one_order(
            container, items, ceilings, order,
            beam_width=beam_width, max_block_placements=max_block_placements,
            min_support_ratio=min_support_ratio, solution_limit=solution_limit,
            deadline=order_deadline,
        )
        for state in states:
            if order_deadline is not None and time.perf_counter() >= order_deadline:
                break
            if auto_item is not None:
                state, _ = complete_state(
                    state, items, ceilings, container, min_support_ratio,
                    mode="UNIFIED_STAGE_MAX", max_additions=500, deadline=order_deadline,
                )
            expanded.append(state)

    unique = {}
    def auto_count(state: SearchState) -> int:
        return state.counts.get(auto_item.sku, 0) if auto_item is not None else 0

    for state in sorted(
        expanded,
        key=lambda value: (
            auto_count(value),
            value.volume,
            -len(value.blocks),
        ),
        reverse=True,
    ):
        unique.setdefault(_signature(state), state)
    selected = list(unique.values())
    return selected[:max(1, solution_limit * 6)], PortfolioMetadata(
        planned_order_count, len(selected), False,
        "reachable-frontier-hard-auto-floor-ordered-sku-search",
    )
