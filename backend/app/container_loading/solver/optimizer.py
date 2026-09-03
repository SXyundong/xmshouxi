from __future__ import annotations

import hashlib
import json
import os
import time

from ..models.block import Block
from ..models.placement import Placement
from ..models.solution import OptimizationResult, SolutionMetrics
from .accessibility import validate_accessibility
from .beam_search import (
    beam_pack_solutions,
    complete_state,
    construct_single_sku_states,
    _layout_compactness,
)
from .block_generator import generate_blocks
from .constraints import validate_solution
from .lns import destroy_states
from .maximal_spaces import spaces_after_blocks
from .quantity_optimizer import (
    auto_fill_quantity_upper_bound,
    legal_max_quantity,
    legal_min_quantity,
    quantity_is_valid,
    quantity_search_info,
    validate_quantity_plan,
)
from .stack_scan import stack_scan_search


SUPPORTED_MODES = {"UNIFIED_STAGE_MAX", "THEORETICAL_MAX", "SEQUENCE_REALISTIC_MAX"}


def _ordered_state(state, items, container, realistic):
    if not realistic:
        return state
    stages = {item.sku: item.effective_loading_stage for item in items}
    state.blocks = sorted(state.blocks, key=lambda entry: (stages[entry[0]["sku"]], entry[1][0], entry[1][1], entry[1][2]))
    state.empty_spaces = spaces_after_blocks(container, state.blocks)
    state.stage_index = max(0, len(set(stages.values()))-1)
    return state


def _expand_state(state, items, container=None):
    item_by_sku = {item.sku: item for item in items}
    placements, blocks = [], []
    for number, (definition, (x, y, z)) in enumerate(state.blocks, 1):
        item = item_by_sku[definition["sku"]]
        stage = item.effective_loading_stage
        block_id = f"{definition['sku']}-B{number:03d}"
        fields = {key: definition[key] for key in (
            "sku", "nx", "ny", "nz", "box_count", "length", "width", "height",
            "orientation", "weight_kg", "volume_m3",
        )}
        blocks.append(Block(block_id=block_id, x=x, y=y, z=z, loading_stage=stage, **fields))
        unit_l = definition.get("unit_length", definition["length"]//definition["nx"])
        unit_w = definition.get("unit_width", definition["width"]//definition["ny"])
        unit_h = definition.get("unit_height", definition["height"]//definition["nz"])
        clearance = getattr(container, "clearance_mm_int", 0) if container is not None else 0
        box_number = 1
        # Head-to-door within each layer is a valid axial loading order.
        for iz in range(definition["nz"]):
            for iy in range(definition["ny"]):
                for ix in range(definition["nx"]):
                    placements.append(Placement(
                        box_id=f"{definition['sku']}-{number:03d}-{box_number:03d}",
                        sku=definition["sku"], factory=item.factory,
                        x=x+ix*(unit_l+clearance), y=y+iy*(unit_w+clearance), z=z+iz*unit_h,
                        length=unit_l, width=unit_w, height=unit_h,
                        orientation=definition["orientation"], weight_kg=item.carton_weight_kg,
                        loading_stage=stage, block_id=block_id,
                    ))
                    box_number += 1
    return placements, blocks


def _cross_sku_x_overlap(blocks):
    return any(
        left.sku != right.sku and left.x < right.x+right.length and left.x+left.length > right.x
        for index, left in enumerate(blocks) for right in blocks[index+1:]
    )


def _partial_cross_section(blocks, container):
    _, width, height = container.dimensions_mm
    return any(block.width*block.height < width*height for block in blocks)


def _result_from_state(state, container, items, mode, upper, min_support_ratio, started,
                       solution_id, solution_name, seed_volume, locally_maximal,
                       *, solution_status="BEST_FOUND", optimization_scope="pattern-portfolio",
                       upper_bound_proven=False, auto_fill_upper_quantity=None, portfolio_candidates=0,
                       audit=None):
    # Keep the legacy mode labels for API/UI compatibility.  The first
    # version uses one staged, physically executable planning model for both.
    realistic = True
    placements, blocks = _expand_state(state, items, container)
    validation, quantities, _ = validate_solution(placements, container, items, mode, min_support_ratio)
    validation["cross_sku_x_overlap"] = _cross_sku_x_overlap(blocks)
    validation["partial_cross_section_blocks"] = _partial_cross_section(blocks, container)
    validation.update(validate_accessibility(placements, container))
    validation["locally_maximal"] = locally_maximal
    # A timed optimisation may return a legal solution before it proves that
    # no further carton can be added.  Local maximality is optimisation
    # metadata, not a geometry validity condition.
    validation["valid"] = validation["valid"] and validation["sequence_valid"]

    item_by_sku = {item.sku: item for item in items}
    loaded_cbm = sum(quantities[item.sku]*item.volume_m3 for item in items)
    gap = max(0.0, (upper-loaded_cbm)/upper*100) if upper else 0.0
    auto_item = next((item for item in items if item.is_auto_fill), None)
    auto_quantity = quantities.get(auto_item.sku, 0) if auto_item else None
    auto_gap = (max(0, auto_fill_upper_quantity-auto_quantity)
                if auto_fill_upper_quantity is not None and auto_quantity is not None else None)
    return OptimizationResult(
        solution_id=solution_id, solution_name=solution_name, mode=mode, mix_policy="FIXED_LAST_STAGE_AUTO",
        clearance_mm=getattr(container, "clearance_mm", 0.0),
        solution_status=solution_status, locally_maximal=locally_maximal, loaded_cbm=round(loaded_cbm, 6),
        physical_utilization=loaded_cbm/container.physical_cbm,
        operational_utilization=loaded_cbm/container.operational_target_cbm,
        total_weight_kg=round(sum(p.weight_kg for p in placements), 3), loaded_boxes=len(placements),
        sku_quantities=quantities, blocks=blocks, placements=placements,
        loading_sequence=[{
            "step": number, "block_id": block.block_id, "sku": block.sku,
            "box_count": block.box_count, "loading_stage": block.loading_stage,
        } for number, block in enumerate(blocks, 1)],
        metrics=SolutionMetrics(
            fragmentation_score=max(0.0, 1.0-loaded_cbm/max(upper, 1e-9)),
            loading_complexity=min(1.0, len(blocks)/max(1, len(placements))),
            balance_score=0.0,
        ),
        upper_bound_cbm=round(upper, 6), upper_bound_proven=upper_bound_proven,
        optimality_gap_percent=round(gap, 3), validation=validation,
        optimization_scope=optimization_scope,
        auto_fill_upper_quantity=auto_fill_upper_quantity,
        auto_fill_gap_boxes=auto_gap,
        portfolio_candidates=portfolio_candidates,
        audit=audit or {},
        solve_time_seconds=round(time.perf_counter()-started, 4), initial_seed_cbm=round(seed_volume, 6),
        search_improvement_cbm=round(max(0.0, loaded_cbm-seed_volume), 6),
    )


def _audit_context(container, items, effective_options, portfolio) -> dict:
    """Build a non-sensitive fingerprint for local/production comparisons."""
    snapshot = {
        "container": {
            "dimensions_mm": container.dimensions_mm,
            "clearance_mm": container.clearance_mm,
            "max_payload": container.max_payload,
            "operational_target_cbm": container.operational_target_cbm,
            "operational_mode": container.operational_mode,
        },
        "items": [
            {
                "sku": item.sku,
                "dimensions_mm": item.dimensions_mm,
                "carton_weight_kg": item.carton_weight_kg,
                "min_quantity": item.min_quantity,
                "max_quantity": item.max_quantity,
                "quantity_step": item.quantity_step,
                "loading_stage": item.effective_loading_stage,
            }
            for item in items
        ],
        "options": effective_options,
    }
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    build_version = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("COMMIT_SHA")
        or "unknown"
    )
    return {
        "algorithm": "v0.4-stack-scan-lookahead",
        "build_version": build_version,
        "input_fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16],
        "effective_options": effective_options,
        "portfolio_scope": portfolio.scope,
        "fixed_candidates": portfolio.fixed_candidates,
        "expanded_candidates": portfolio.expanded_candidates,
        "cp_sat_selected": portfolio.selected_by_cp_sat,
    }


def _state_signature(state, items):
    counts = tuple(state.counts.get(item.sku, 0) for item in items)
    geometry = tuple(sorted((block["sku"], x, y, z, block["length"], block["width"], block["height"])
                            for block, (x, y, z) in state.blocks))
    return counts, geometry


def _select_diverse_states(states, items, container, limit):
    unique = {}
    for state in sorted(
        states,
        key=lambda candidate: (candidate.volume, *_layout_compactness(candidate, items)),
        reverse=True,
    ):
        if quantity_is_valid(state.counts, items, container):
            unique.setdefault(_state_signature(state, items), state)
    ranked = list(unique.values())
    if not ranked:
        return []
    selected = [ranked[0]]

    # Always expose the best genuinely non-zoned geometry if one was found.
    for state in ranked[1:]:
        _, blocks = _expand_state(state, items, container)
        if _cross_sku_x_overlap(blocks) and _state_signature(state, items) != _state_signature(selected[0], items):
            selected.append(state)
            break
    # Then prefer different quantity vectors before layout-only variants.
    quantity_vectors = {tuple(selected_state.counts.get(item.sku, 0) for item in items) for selected_state in selected}
    for state in ranked[1:]:
        vector = tuple(state.counts.get(item.sku, 0) for item in items)
        if vector not in quantity_vectors:
            selected.append(state)
            quantity_vectors.add(vector)
        if len(selected) >= limit:
            return selected
    for state in ranked[1:]:
        if state not in selected:
            selected.append(state)
        if len(selected) >= limit:
            break
    return selected


def optimize_container(container, items, mode="THEORETICAL_MAX", options=None):
    options = options or {}
    mode = str(mode).upper()
    if mode in {"FACTORY_REALISTIC_MAX", "THEORETICAL_MAX", "SEQUENCE_REALISTIC_MAX"}:
        mode = "UNIFIED_STAGE_MAX"
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode must be one of {sorted(SUPPORTED_MODES)}")
    if len({item.sku for item in items}) != len(items):
        raise ValueError("SKU identifiers must be unique")
    started = time.perf_counter()
    # Legacy mode names are retained for compatibility; both use the unified
    # staged physical loading model in the first version.
    realistic = True
    min_support_ratio = float(options.get("min_support_ratio", 0.8))
    beam_width = int(options.get("beam_width", 18))
    max_placements = int(options.get("max_block_placements", 48))
    solution_limit = max(1, min(8, int(options.get("solution_limit", 4))))
    time_limit = max(1.0, float(options.get("time_limit_seconds", 300.0)))
    deadline = started+time_limit
    lns_rounds = max(0, int(options.get("lns_rounds", 6)))
    fixed_max_blocks = max(1, int(options.get("fixed_max_blocks_per_sku", 6)))
    portfolio_limit = max(2, int(options.get("stage_portfolio_limit", 6)))
    effective_options = {
        "beam_width": beam_width,
        "max_block_placements": max_placements,
        "solution_limit": solution_limit,
        "time_limit_seconds": time_limit,
        "lns_rounds": lns_rounds,
        "max_blocks_per_sku": int(options.get("max_blocks_per_sku", 140)),
        "fixed_max_blocks_per_sku": fixed_max_blocks,
        "stage_portfolio_limit": portfolio_limit,
        "min_support_ratio": min_support_ratio,
    }

    validate_quantity_plan(items)
    cp_candidate, cp_upper, cp_proven = quantity_search_info(items, container)
    if not cp_candidate:
        raise ValueError("minimum quantities violate volume or payload constraints")
    physical_upper = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm
    upper = min(cp_upper, physical_upper)

    def state_is_fully_valid(state):
        placements, _ = _expand_state(state, items, container)
        validation, _, _ = validate_solution(placements, container, items, mode, min_support_ratio)
        validation.update(validate_accessibility(placements, container))
        validation["valid"] = validation["valid"] and validation["sequence_valid"]
        return validation["valid"]

    portfolio_states, portfolio = stack_scan_search(
        container, items,
        beam_width=beam_width,
        max_block_placements=max_placements,
        min_support_ratio=min_support_ratio,
        solution_limit=solution_limit,
        deadline=deadline,
        max_blocks_per_sku=int(options.get("max_blocks_per_sku", 140)),
        fixed_max_blocks_per_sku=fixed_max_blocks,
        portfolio_limit=portfolio_limit,
    )
    selected_states = []
    for state in portfolio_states:
        if state_is_fully_valid(state):
            selected_states.append(state)
        if len(selected_states) >= solution_limit:
            break
    if not selected_states:
        fixed_requirements = "、".join(
            f"{item.sku}={legal_min_quantity(item)}箱"
            for item in items
            if not item.is_auto_fill
        ) or "无固定数量商品"
        raise ValueError(
            f"统一阶段装柜无法满足固定数量：{fixed_requirements}。"
            "请检查固定数量、装载顺序、柜体尺寸和横向缝隙。"
        )

    auto_item = next((item for item in items if item.is_auto_fill), None)
    auto_upper = auto_fill_quantity_upper_bound(items, container)
    seed_volume = max((state.volume for state in selected_states), default=0.0)
    solution_status = "PORTFOLIO_OPTIMAL" if portfolio.selected_by_cp_sat else "BEST_FOUND"
    audit = _audit_context(container, items, effective_options, portfolio)

    def state_is_locally_maximal(state):
        """Confirm the returned AUTO layout has no legal one-step addition."""
        if auto_item is None:
            return True
        ceilings = {item.sku: legal_max_quantity(item, container) for item in items}
        probe, additions = complete_state(
            state, items, ceilings, container, min_support_ratio,
            mode="UNIFIED_STAGE_MAX", max_additions=1,
        )
        return additions == 0 and probe.counts.get(auto_item.sku, 0) == state.counts.get(auto_item.sku, 0)

    results = []
    for index, state in enumerate(selected_states, 1):
        _, preview_blocks = _expand_state(state, items, container)
        mixed = _cross_sku_x_overlap(preview_blocks)
        if index == 1:
            name = "最高装载体积"
        elif mixed:
            name = "交错混装候选"
        else:
            name = f"候选方案 {index}"
        result = _result_from_state(
            state, container, items, mode, upper, min_support_ratio, started,
            f"{mode}-{index}", name, seed_volume, state_is_locally_maximal(state),
            solution_status=solution_status,
            optimization_scope=portfolio.scope,
            upper_bound_proven=False,
            auto_fill_upper_quantity=auto_upper,
            portfolio_candidates=portfolio.expanded_candidates,
            audit={**audit, "selected_candidate_rank": index + 1},
        )
        if result.validation["valid"]:
            results.append(result)
    if not results:
        raise ValueError("candidate layouts failed final geometry or loading-sequence validation")

    best = results[0]
    best.alternatives = [candidate.model_dump(exclude={"alternatives"}) for candidate in results[1:]]
    best.solve_time_seconds = round(time.perf_counter()-started, 4)
    return best
