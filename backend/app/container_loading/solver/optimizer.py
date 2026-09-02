from __future__ import annotations

import time

from ..models.block import Block
from ..models.placement import Placement
from ..models.solution import OptimizationResult, SolutionMetrics
from .accessibility import validate_accessibility
from .beam_search import (
    beam_pack_solutions,
    complete_state,
    construct_equal_slab_state,
    construct_mosaic_states,
    construct_single_sku_states,
)
from .block_generator import generate_blocks
from .constraints import validate_solution
from .lns import destroy_states
from .maximal_spaces import spaces_after_blocks
from .quantity_optimizer import legal_max_quantity, quantity_is_valid, quantity_search_info, validate_quantity_plan


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
                       solution_id, solution_name, seed_volume, locally_maximal, upper_bound_proven=True):
    # Keep the legacy mode labels for API/UI compatibility.  The first
    # version uses one staged, physically executable planning model for both.
    realistic = True
    placements, blocks = _expand_state(state, items, container)
    validation, quantities, _ = validate_solution(placements, container, items, mode, min_support_ratio)
    validation["cross_sku_x_overlap"] = _cross_sku_x_overlap(blocks)
    validation["partial_cross_section_blocks"] = _partial_cross_section(blocks, container)
    validation.update(validate_accessibility(placements, container))
    validation["locally_maximal"] = locally_maximal
    validation["valid"] = validation["valid"] and validation["sequence_valid"] and locally_maximal

    item_by_sku = {item.sku: item for item in items}
    loaded_cbm = sum(quantities[item.sku]*item.volume_m3 for item in items)
    gap = max(0.0, (upper-loaded_cbm)/upper*100) if upper else 0.0
    status = "PROVEN_OPTIMAL" if gap <= 1e-9 else "BEST_FOUND"
    return OptimizationResult(
        solution_id=solution_id, solution_name=solution_name, mode=mode, mix_policy="FIXED_LAST_STAGE_AUTO",
        clearance_mm=getattr(container, "clearance_mm", 0.0),
        solution_status=status, locally_maximal=locally_maximal, loaded_cbm=round(loaded_cbm, 6),
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
        solve_time_seconds=round(time.perf_counter()-started, 4), initial_seed_cbm=round(seed_volume, 6),
        search_improvement_cbm=round(max(0.0, loaded_cbm-seed_volume), 6),
    )


def _state_signature(state, items):
    counts = tuple(state.counts.get(item.sku, 0) for item in items)
    geometry = tuple(sorted((block["sku"], x, y, z, block["length"], block["width"], block["height"])
                            for block, (x, y, z) in state.blocks))
    return counts, geometry


def _select_diverse_states(states, items, container, limit):
    unique = {}
    for state in sorted(states, key=lambda candidate: candidate.volume, reverse=True):
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

    validate_quantity_plan(items)
    cp_candidate, cp_upper, cp_proven = quantity_search_info(items, container)
    if not cp_candidate:
        raise ValueError("minimum quantities violate volume or payload constraints")
    # The CP incumbent is one candidate, never a per-SKU search ceiling.
    quantity_ceiling = {item.sku: legal_max_quantity(item, container) for item in items}
    physical_upper = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm
    upper = min(cp_upper, physical_upper)

    block_defs = []
    for item in items:
        block_defs.extend(generate_blocks(item, container, int(options.get("max_blocks_per_sku", 100))))

    candidates = []
    slab = construct_equal_slab_state(items, container)
    if slab is not None:
        candidates.append(_ordered_state(slab, items, container, realistic))
    mosaics = [_ordered_state(state, items, container, realistic)
               for state in construct_mosaic_states(items, container, max(6, solution_limit*2))]
    candidates.extend(mosaics)
    candidates.extend(_ordered_state(state, items, container, realistic)
                      for state in construct_single_sku_states(items, container))
    seed_candidates = list(candidates)
    seed_volume = max((state.volume for state in candidates if quantity_is_valid(state.counts, items, container)), default=0.0)

    # Empty search discovers layouts without a seed. Seeded searches refine the
    # slab and mosaic lower bounds through their actual EMS residual spaces.
    empty_solutions = beam_pack_solutions(
        items, quantity_ceiling, container, block_defs, beam_width, max_placements,
        min_support_ratio, None, mode, archive_limit=solution_limit*8, deadline=deadline,
    )
    candidates.extend(empty_solutions)
    if mosaics:
        candidates.extend(beam_pack_solutions(
            items, quantity_ceiling, container, block_defs, max(8, beam_width//2), max(8, max_placements//2),
            min_support_ratio, mosaics[:min(3, len(mosaics))], mode, archive_limit=solution_limit*6,
            deadline=deadline,
        ))

    # Independent move validation is only needed during completion when
    # advanced stacking fields are active; ordinary benchmark items use the
    # faster geometric path and are independently validated afterwards.
    advanced_stacking = any(item.stack_limit is not None or item.max_top_load_kg is not None or item.fragile
                            for item in items)

    def completion_move_valid(base_state, block, position):
        if not advanced_stacking:
            return True
        x, y, z = position
        trial = type(base_state)(
            blocks=base_state.blocks+[(block, position)], counts=base_state.counts.copy(),
            empty_spaces=base_state.empty_spaces, volume=base_state.volume+block["volume_m3"],
            weight=base_state.weight+block["weight_kg"], stage_index=base_state.stage_index,
        )
        trial.counts[block["sku"]] = trial.counts.get(block["sku"], 0)+block["box_count"]
        placements, _ = _expand_state(trial, items, container)
        validation, _, _ = validate_solution(placements, container, items, mode, min_support_ratio)
        return validation["valid"]

    def state_is_fully_valid(state):
        placements, _ = _expand_state(state, items, container)
        validation, _, _ = validate_solution(placements, container, items, mode, min_support_ratio)
        validation.update(validate_accessibility(placements, container))
        validation["valid"] = validation["valid"] and validation["sequence_valid"]
        return validation["valid"]

    # Completion is a mandatory contract, not an optional heuristic. Complete
    # the strongest diverse states before and after LNS.
    unique_candidates = {}
    completion_candidate_limit = max(len(seed_candidates), int(options.get("completion_candidate_limit", 24)))
    candidate_order = seed_candidates+sorted(candidates, key=lambda candidate: candidate.volume, reverse=True)
    for state in candidate_order:
        if quantity_is_valid(state.counts, items, container) and state_is_fully_valid(state):
            unique_candidates.setdefault(_state_signature(state, items), state)
        if len(unique_candidates) >= completion_candidate_limit:
            break
    completed_candidates = []
    for state in unique_candidates.values():
        completed, _ = complete_state(
            state, items, quantity_ceiling, container, min_support_ratio, mode,
            max_additions=int(options.get("completion_max_additions", 500)),
            move_validator=completion_move_valid,
        )
        probe, probe_additions = complete_state(
            completed, items, quantity_ceiling, container, min_support_ratio, mode,
            max_additions=1, move_validator=completion_move_valid,
        )
        if probe_additions == 0 and state_is_fully_valid(completed):
            completed_candidates.append(completed)

    # Deterministic LNS destroys suffix/door/top regions and repairs them with
    # the same EMS beam search, keeping the best incumbent throughout.
    lns_pool = list(completed_candidates)
    no_improvement = 0
    best_before_lns = max((state.volume for state in lns_pool), default=0.0)
    for _ in range(lns_rounds):
        if time.perf_counter() >= deadline or not lns_pool:
            break
        sources = sorted(lns_pool, key=lambda state: state.volume, reverse=True)[:2]
        destroyed = []
        for source in sources:
            destroyed.extend(destroy_states(source, items, container, mode))
        repaired = beam_pack_solutions(
            items, quantity_ceiling, container, block_defs, max(10, beam_width//2),
            max(12, max_placements//2), min_support_ratio, destroyed, mode,
            archive_limit=max(8, solution_limit*4), deadline=deadline,
        ) if destroyed else []
        improved_this_round = False
        for state in repaired:
            if not quantity_is_valid(state.counts, items, container):
                continue
            completed, _ = complete_state(
                state, items, quantity_ceiling, container, min_support_ratio, mode,
                max_additions=int(options.get("completion_max_additions", 500)),
                move_validator=completion_move_valid,
            )
            _, additions = complete_state(
                completed, items, quantity_ceiling, container, min_support_ratio, mode,
                max_additions=1, move_validator=completion_move_valid,
            )
            if additions == 0 and state_is_fully_valid(completed):
                lns_pool.append(completed)
                if completed.volume > best_before_lns+1e-9:
                    best_before_lns = completed.volume
                    improved_this_round = True
        no_improvement = 0 if improved_this_round else no_improvement+1
        if no_improvement >= int(options.get("lns_no_improvement_rounds", 3)):
            break

    selected_states = _select_diverse_states(completed_candidates+lns_pool, items, container, solution_limit)
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
        # The state was completed to a small-block fixed point above.
        result = _result_from_state(
            state, container, items, mode, upper, min_support_ratio, started,
            f"{mode}-{index}", name, seed_volume, True, True,
        )
        if result.validation["valid"]:
            results.append(result)
    if not results:
        raise ValueError("candidate layouts failed final geometry or loading-sequence validation")

    best = results[0]
    best.alternatives = [candidate.model_dump(exclude={"alternatives"}) for candidate in results[1:]]
    best.solve_time_seconds = round(time.perf_counter()-started, 4)
    return best
