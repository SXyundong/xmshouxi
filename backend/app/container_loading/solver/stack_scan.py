"""V0.7 ordered-SKU staged search.

Each factory stage enumerates its SKU orders.  A SKU is fully placed before
the next SKU in that order opens; only the final AUTO SKU can continue without
a requested quantity.  Candidate generation remains three-dimensional, but
same-stage interleaving is intentionally not an optimisation variable.
"""

from __future__ import annotations

from itertools import product, permutations
import time

from .beam_search import SearchState, beam_pack_solutions, complete_state
from .maximal_spaces import initial_space
from .quantity_optimizer import legal_max_quantity
from .stage_portfolio import PortfolioMetadata, _copy_for_all_items, _exact_fixed_stage_patterns


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
    recovery_deadline = deadline
    ordered_deadline = deadline
    if deadline is not None:
        # Keep a bounded recovery window.  A sequential order may be a poor
        # fit for a particular carton geometry; returning a known-feasible
        # layout is preferable to falsely declaring the fixed request
        # impossible while the user adjusts the SKU order.
        remaining = max(0.0, deadline-time.perf_counter())
        recovery_deadline = deadline
        ordered_deadline = min(deadline, time.perf_counter()+min(60.0, max(2.0, remaining*0.3)))
        # Short API/test budgets must first preserve fixed-quantity feasibility.
        # The production job uses 300 seconds and evaluates the ordered plans.
        if remaining < 45.0:
            plans = []
    for order in plans:
        if ordered_deadline is not None and time.perf_counter() >= ordered_deadline:
            break
        states = beam_pack_solutions(
            items, ceilings, container, [], 8, min(48, max_block_placements),
            min_support_ratio, None, "UNIFIED_STAGE_MAX",
            archive_limit=max(8, solution_limit * 6), deadline=ordered_deadline,
            stage_sku_orders=order,
        )
        for state in states:
            if ordered_deadline is not None and time.perf_counter() >= ordered_deadline:
                break
            if auto_item is not None:
                state, _ = complete_state(
                    state, items, ceilings, container, min_support_ratio,
                    mode="UNIFIED_STAGE_MAX", max_additions=500, deadline=ordered_deadline,
                )
            expanded.append(state)

    recovery_used = not plans
    if not expanded and (recovery_deadline is None or time.perf_counter() < recovery_deadline):
        # V0.6's general beam remains a feasibility safety net only.  It is
        # not scored as an ordered-SKU optimum and is surfaced in the audit.
        recovery_used = True
        fixed_items = [item for item in items if not item.is_auto_fill]
        fixed_ceilings = {item.sku: legal_max_quantity(item, container) for item in fixed_items}
        recovered = _exact_fixed_stage_patterns(
            fixed_items, container, limit=max(4, portfolio_limit * 4),
        )
        if not recovered:
            recovered = beam_pack_solutions(
                fixed_items, fixed_ceilings, container, [], max(beam_width, 32), max_block_placements,
                min_support_ratio, None, "UNIFIED_STAGE_MAX",
                archive_limit=max(12, solution_limit * 8), deadline=recovery_deadline,
                restrict_fixed_stage_x=True,
            )
        for state in recovered:
            if recovery_deadline is not None and time.perf_counter() >= recovery_deadline:
                break
            state = _copy_for_all_items(state, items, fixed_items)
            if auto_item is not None:
                state, _ = complete_state(
                    state, items, ceilings, container, min_support_ratio,
                    mode="UNIFIED_STAGE_MAX", max_additions=500, deadline=recovery_deadline,
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
        "ordered-sku-stage-search+feasibility-recovery" if recovery_used else "ordered-sku-stage-search",
    )
