"""v0.4 stack-style staged search.

Fixed-stage layouts are generated as cross-section patterns first. Each
pattern is then tested with a small supported top seed before the existing
carton-level completion search fills the final auto stage. This keeps the
operational rule simple while making the future-stage quantity part of the
layout decision.
"""

from __future__ import annotations

import time

from .beam_search import SearchState, beam_pack_solutions
from .maximal_spaces import initial_space
from .quantity_optimizer import legal_max_quantity
from .stage_portfolio import (
    PortfolioMetadata,
    _copy_for_all_items,
    _exact_fixed_stage_patterns,
    _top_fill_seeds,
)


def _signature(state: SearchState) -> tuple:
    return tuple(
        (block["sku"], position, block["nx"], block["ny"], block["nz"], block["orientation"])
        for block, position in state.blocks
    )


def _fixed_candidates(items: list, container, portfolio_limit: int) -> list[SearchState]:
    fixed_items = [item for item in items if not item.is_auto_fill]
    if not fixed_items:
        return [SearchState(counts={item.sku: 0 for item in items}, empty_spaces=initial_space(container))]
    # The exact pattern generator is still bounded for runtime, but its first
    # candidates are cross-section layouts rather than long SKU walls. Keep
    # several patterns so the later auto fill can choose the best future space.
    patterns = _exact_fixed_stage_patterns(
        fixed_items, container, limit=max(4, min(12, portfolio_limit * 2))
    )
    unique = {}
    for state in patterns:
        unique.setdefault(_signature(state), state)
    return list(unique.values())


def stack_scan_search(container, items: list, *, beam_width: int, max_block_placements: int,
                      min_support_ratio: float, solution_limit: int, deadline: float | None,
                      max_blocks_per_sku: int = 140, fixed_max_blocks_per_sku: int = 6,
                      portfolio_limit: int = 6) -> tuple[list[SearchState], PortfolioMetadata]:
    """Search width/height-first fixed patterns and look ahead into auto fill."""
    fixed_items = [item for item in items if not item.is_auto_fill]
    auto_item = next((item for item in items if item.is_auto_fill), None)
    fixed_states = _fixed_candidates(items, container, portfolio_limit)
    if auto_item is None:
        return fixed_states[:max(1, solution_limit * 6)], PortfolioMetadata(
            len(fixed_states), len(fixed_states), False, "stack-scan-lookahead"
        )

    # Top seeds are deliberately evaluated before empty seeds. They expose
    # usable vertical space above the current factory without reserving a
    # permanent side lane for it.
    seeds = []
    for fixed_state in fixed_states[:max(4, min(12, portfolio_limit * 2))]:
        seed = _copy_for_all_items(fixed_state, items, fixed_items)
        seeds.extend(_top_fill_seeds(seed, items, auto_item, container, limit=1))
        seeds.append(seed)

    expanded = []
    ceilings = {item.sku: legal_max_quantity(item, container) for item in items}
    for index, seed in enumerate(seeds):
        if deadline is not None and time.perf_counter() >= deadline:
            break
        remaining = max(0.0, deadline-time.perf_counter()) if deadline is not None else 30.0
        seeds_left = max(1, len(seeds)-index)
        seed_deadline = None if deadline is None else min(
            deadline, time.perf_counter() + max(0.75, remaining / seeds_left)
        )
        expanded.extend(beam_pack_solutions(
            items, ceilings, container, [],
            max(beam_width, 32), max_block_placements, min_support_ratio,
            [seed], "UNIFIED_STAGE_MAX",
            archive_limit=max(6, solution_limit * 4), deadline=seed_deadline,
        ))

    unique = {}
    for state in sorted(
        expanded,
        key=lambda value: (
            value.counts.get(auto_item.sku, 0),
            value.volume,
            -len(value.blocks),
        ),
        reverse=True,
    ):
        unique.setdefault(_signature(state), state)
    selected = list(unique.values())
    return selected[:max(1, solution_limit * 6)], PortfolioMetadata(
        len(fixed_states), len(selected), False, "stack-scan-lookahead"
    )
