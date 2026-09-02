from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
import time

from .accessibility import swept_path_clear
from .block_generator import generate_blocks_for_space, _vertical_limit, _axis_capacity, _axis_size
from .geometry import within, overlaps, support_ratio
from .maximal_spaces import EmptySpace, initial_space, spaces_after_blocks, subtract_placement
from .orientation import orientations
from .quantity_optimizer import legal_max_quantity, legal_min_quantity, quantity_is_valid


@dataclass(frozen=True, slots=True)
class Rect3D:
    x: int
    y: int
    z: int
    length: int
    width: int
    height: int


@dataclass
class SearchState:
    blocks: list = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    empty_spaces: list[EmptySpace] = field(default_factory=list)
    volume: float = 0.0
    weight: float = 0.0
    stage_index: int = 0
    score: tuple = field(default_factory=tuple)


def _grid_block(item, orientation, dims, nx, ny, nz, clearance_mm=0):
    l, w, h = dims
    clearance = max(0, round(float(clearance_mm)))
    count = nx * ny * nz
    return {
        "sku": item.sku, "nx": nx, "ny": ny, "nz": nz, "box_count": count,
        "length": _axis_size(nx, l, clearance), "width": _axis_size(ny, w, clearance),
        "height": nz*h, "unit_length": l, "unit_width": w, "unit_height": h,
        "orientation": orientation,
        "weight_kg": count*item.carton_weight_kg, "volume_m3": count*item.volume_m3,
    }


def _state_from_blocks(items, container, blocks, stage_index=0):
    counts = {item.sku: 0 for item in items}
    volume = weight = 0.0
    for block, _ in blocks:
        counts[block["sku"]] += block["box_count"]
        volume += block["volume_m3"]
        weight += block["weight_kg"]
    return SearchState(blocks=list(blocks), counts=counts, empty_spaces=spaces_after_blocks(container, blocks),
                       volume=volume, weight=weight, stage_index=stage_index)


def construct_single_sku_states(items, container):
    """Feasible lower bounds for cases where all other SKUs are optional."""
    cl, cw, ch = container.dimensions_mm
    clearance = getattr(container, "clearance_mm_int", 0)
    states = []
    for item in items:
        if any(other.sku != item.sku and legal_min_quantity(other) > 0 for other in items):
            continue
        best = None
        maximum = legal_max_quantity(item, container)
        for orientation, dims in orientations(item):
            l, w, h = dims
            nx, ny, nz = _axis_capacity(cl, l, clearance), _axis_capacity(cw, w, clearance), _vertical_limit(item, ch // h)
            nx = min(nx, maximum // max(1, ny*nz))
            if nx <= 0 or ny <= 0 or nz <= 0:
                continue
            block = _grid_block(item, orientation, dims, nx, ny, nz, clearance)
            if block["box_count"] % item.quantity_step:
                continue
            if best is None or block["volume_m3"] > best["volume_m3"]:
                best = block
        if best:
            states.append(_state_from_blocks(items, container, [(best, (0, 0, 0))]))
    return states


def construct_equal_slab_state(items, container):
    """Legacy X-slab lower bound retained as one candidate, never as a restriction."""
    cl, cw, ch = container.dimensions_mm
    clearance = getattr(container, "clearance_mm_int", 0)
    cursor = 0
    blocks = []
    for index, item in enumerate(items):
        segment = (cl-cursor) // (len(items)-index)
        best = None
        maximum = legal_max_quantity(item, container)
        for orientation, dims in orientations(item):
            l, w, h = dims
            nx, ny, nz = _axis_capacity(segment, l, clearance), _axis_capacity(cw, w, clearance), _vertical_limit(item, ch // h)
            nx = min(nx, maximum // max(1, ny*nz))
            if nx <= 0 or ny <= 0 or nz <= 0:
                continue
            block = _grid_block(item, orientation, dims, nx, ny, nz, clearance)
            if block["box_count"] < legal_min_quantity(item) or block["box_count"] % item.quantity_step:
                continue
            if best is None or block["volume_m3"] > best["volume_m3"]:
                best = block
        if best is None:
            return None
        blocks.append((best, (cursor, 0, 0)))
        cursor += best["length"] + (clearance if index < len(items)-1 else 0)
    return _state_from_blocks(items, container, blocks)


def _lane_candidates(item, container, limit=18):
    """Blocks that can form one partial cross-section lane for a SKU."""
    cl, cw, ch = container.dimensions_mm
    clearance = getattr(container, "clearance_mm_int", 0)
    minimum, maximum = legal_min_quantity(item), legal_max_quantity(item, container)
    candidates = []
    for orientation, dims in orientations(item):
        l, w, h = dims
        max_nx, max_ny, max_nz = _axis_capacity(cl, l, clearance), _axis_capacity(cw, w, clearance), _vertical_limit(item, ch//h)
        for ny in range(1, max_ny+1):
            for nz in range(1, max_nz+1):
                layer = ny*nz
                if layer <= 0:
                    continue
                low_nx = max(1, (minimum + layer - 1)//layer)
                high_nx = min(max_nx, maximum//layer)
                if low_nx > high_nx:
                    continue
                for nx in {low_nx, high_nx, max(low_nx, (low_nx+high_nx)//2)}:
                    block = _grid_block(item, orientation, dims, nx, ny, nz, clearance)
                    if block["box_count"] < minimum or block["box_count"] > maximum:
                        continue
                    if block["box_count"] % item.quantity_step:
                        continue
                    candidates.append(block)
    # Volume first, but preserve narrow lanes so multiple SKUs can share Y.
    candidates.sort(key=lambda b: (b["volume_m3"], -b["width"], b["height"]), reverse=True)
    selected = candidates[:max(4, limit//2)]
    for block in sorted(candidates, key=lambda b: (b["width"], -b["volume_m3"])):
        if block not in selected:
            selected.append(block)
        if len(selected) >= limit:
            break
    return selected


def construct_mosaic_states(items, container, limit=8):
    """Build non-zoned layouts where SKU X-ranges overlap in Y lanes.

    These are real lower bounds and starting points for EMS filling. They prove
    that a partial cross-section is part of the production search, rather than
    being a toy-only capability.
    """
    _, cw, _ = container.dimensions_mm
    clearance = getattr(container, "clearance_mm_int", 0)
    required = [item for item in items if legal_min_quantity(item) > 0]
    optional = [item for item in items if legal_min_quantity(item) == 0]
    selected_items = required + optional
    if not selected_items:
        return []
    orders = [selected_items]
    if len(selected_items) <= 7:
        orders.extend(list(permutations(selected_items))[:min(12, 2*len(selected_items)+2)])
    candidates_by_sku = {item.sku: _lane_candidates(item, container) for item in selected_items}
    layouts = []
    for order in orders:
        partial = [(0, [], 0.0)]
        for item in order:
            options = candidates_by_sku[item.sku]
            next_partial = []
            if legal_min_quantity(item) == 0:
                next_partial.extend(partial)
            for used_width, blocks, volume in partial:
                for block in options:
                    separator = clearance if used_width > 0 else 0
                    if used_width + separator + block["width"] <= cw:
                        y = used_width + separator
                        next_partial.append((y+block["width"], blocks+[(block, (0, y, 0))],
                                             volume+block["volume_m3"]))
            next_partial.sort(key=lambda value: (value[2], value[0]), reverse=True)
            # Width buckets avoid losing narrow combinations too early.
            kept, buckets = [], {}
            for candidate in next_partial:
                bucket = candidate[0]//100
                if buckets.get(bucket, 0) < 3:
                    kept.append(candidate)
                    buckets[bucket] = buckets.get(bucket, 0)+1
                if len(kept) >= 80:
                    break
            partial = kept
            if not partial:
                break
        for _, blocks, _ in partial[:4]:
            state = _state_from_blocks(items, container, blocks)
            if quantity_is_valid(state.counts, items, container):
                layouts.append(state)
    unique = {}
    for state in sorted(layouts, key=lambda s: s.volume, reverse=True):
        signature = tuple((block["sku"], block["width"], block["height"], block["length"])
                          for block, _ in state.blocks)
        unique.setdefault(signature, state)
        if len(unique) >= limit:
            break
    return list(unique.values())


def _placed_rectangles(state):
    return [Rect3D(x, y, z, block["length"], block["width"], block["height"])
            for block, (x, y, z) in state.blocks]


def _stage_x_bounds(state, item, container, all_items):
    """Return the current stage's allowed X band.

    Earlier stages occupy the head-side part of the container.  A stage may
    widen across Y/Z at its current X frontier, then advance that frontier;
    it cannot jump over an empty longitudinal gap.  This keeps a factory's
    cargo compact while preserving the existing EMS geometry search.
    """
    stage = item.effective_loading_stage
    clearance = getattr(container, "clearance_mm_int", 0)
    stage_by_sku = {candidate.sku: candidate.effective_loading_stage for candidate in all_items}
    previous = [
        (block, position)
        for block, position in state.blocks
        if stage_by_sku.get(block["sku"], stage) < stage
    ]
    previous_end = max((position[0] + block["length"] for block, position in previous), default=0)
    stage_start = previous_end + (clearance if previous else 0)
    current = [
        (block, position)
        for block, position in state.blocks
        if stage_by_sku.get(block["sku"], stage) == stage
    ]
    frontier = max((position[0] + block["length"] for block, position in current), default=stage_start)
    return stage_start, frontier


def _positions(space, block, occupied=None, exhaustive=False):
    if block["length"] > space.length or block["width"] > space.width or block["height"] > space.height:
        return []
    xs = {space.x, space.x + space.length - block["length"]}
    ys = {space.y, space.y + space.width - block["width"]}
    if exhaustive and occupied:
        for placed in occupied:
            xs.update((placed.x+placed.length, placed.x-block["length"]))
            ys.update((placed.y+placed.width, placed.y-block["width"]))
        xs = {x for x in xs if space.x <= x <= space.x+space.length-block["length"]}
        ys = {y for y in ys if space.y <= y <= space.y+space.width-block["width"]}
    return sorted({(x, y, space.z) for x in xs for y in ys}, key=lambda p: (p[2], p[0], p[1]))


def _block_pool_for_item(block_defs, item, remaining):
    blocks = [b for b in block_defs if b["sku"] == item.sku and b["box_count"] <= remaining]
    if not blocks:
        return []
    # Preserve large blocks plus count/shape diversity for EMS holes.
    by_volume = sorted(blocks, key=lambda b: (b["volume_m3"], b["box_count"]), reverse=True)[:8]
    by_width = sorted(blocks, key=lambda b: (b["width"], -b["volume_m3"]))[:4]
    by_height = sorted(blocks, key=lambda b: (b["height"], -b["volume_m3"]))[:4]
    near_remaining = sorted(blocks, key=lambda b: (abs(remaining-b["box_count"]), -b["volume_m3"]))[:4]
    result = []
    for block in by_volume+by_width+by_height+near_remaining:
        if block not in result:
            result.append(block)
    return result


def _door_accepts_block(block, item, container):
    if container.door_width is None or container.door_height is None:
        return True
    unit_width = block.get("unit_width", block["width"]//block["ny"])
    unit_height = block.get("unit_height", block["height"]//block["nz"])
    clearance = getattr(container, "clearance_mm_int", 0)
    return (unit_width + 2*clearance <= round(container.door_width*10) and
            unit_height <= round(container.door_height*10))


def _moves(state, eligible_items, quantity, container, min_support_ratio, limit, realistic=False,
           filler_only=False, all_items=None):
    occupied = _placed_rectangles(state)
    moves = []
    for space in state.empty_spaces:
        for item in eligible_items:
            maximum = min(quantity.get(item.sku, legal_max_quantity(item, container)), legal_max_quantity(item, container))
            remaining = maximum-state.counts.get(item.sku, 0)
            if remaining <= 0:
                continue
            blocks = generate_blocks_for_space(
                item, space, remaining, 28 if filler_only else 20, filler_only,
                getattr(container, "clearance_mm_int", 0),
            )
            for block in blocks:
                if realistic and not _door_accepts_block(block, item, container):
                    continue
                for x, y, z in _positions(space, block, occupied, filler_only):
                    if realistic:
                        stage_start, frontier = _stage_x_bounds(state, item, container, all_items or eligible_items)
                        if x < stage_start or x > frontier + getattr(container, "clearance_mm_int", 0):
                            continue
                    if not within(x, y, z, block["length"], block["width"], block["height"], container):
                        continue
                    probe = Rect3D(x, y, z, block["length"], block["width"], block["height"])
                    if any(overlaps(probe, existing, getattr(container, "clearance_mm_int", 0))
                           for existing in occupied):
                        continue
                    if support_ratio(x, y, z, block["length"], block["width"], occupied) + 1e-9 < min_support_ratio:
                        continue
                    if realistic and not swept_path_clear(x, y, z, block["length"], block["width"],
                                                           block["height"], occupied, container):
                        continue
                    leftover = space.volume - block["length"]*block["width"]*block["height"]
                    contact = int(x == 0) + int(y == 0) + int(z == 0)
                    moves.append((block, (x, y, z), leftover, contact))
    if realistic:
        # Within one loading stage, use the width/height cross-section before
        # extending the cargo band along the container length.
        moves.sort(key=lambda move: (
            move[0]["width"] * move[0]["height"],
            move[0]["width"],
            -move[1][0],
            -move[1][1],
            move[0]["volume_m3"],
            move[3],
            -move[2],
        ), reverse=True)
    else:
        moves.sort(key=lambda move: (move[0]["volume_m3"], move[3], -move[2]), reverse=True)
    chosen, seen_skus = [], set()
    for move in moves:
        if move[0]["sku"] not in seen_skus:
            chosen.append(move)
            seen_skus.add(move[0]["sku"])
    for move in moves:
        if move not in chosen:
            chosen.append(move)
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def _minimum_progress(state, items):
    completions = []
    satisfied = 0
    for item in items:
        minimum = legal_min_quantity(item)
        if minimum == 0:
            continue
        count = state.counts.get(item.sku, 0)
        completions.append(min(1.0, count/minimum))
        satisfied += int(count >= minimum)
    return satisfied, sum(completions), min(completions, default=1.0)


def _state_score(state, items, all_stages, realistic):
    valid = quantity_is_valid(state.counts, items, _state_score.container)
    satisfied, completion_sum, minimum_completion = _minimum_progress(state, items)
    stage_progress = state.stage_index/len(all_stages) if realistic and all_stages else 1.0
    largest_space = max((space.volume for space in state.empty_spaces), default=0)
    return (int(valid), satisfied, round(completion_sum, 6), round(minimum_completion, 6),
            round(state.volume, 9), round(stage_progress, 6), largest_space, -len(state.blocks))


def _signature(state, items):
    counts = tuple(state.counts.get(item.sku, 0) for item in items)
    geometry = tuple(sorted((block["sku"], x, y, z, block["length"], block["width"], block["height"])
                            for block, (x, y, z) in state.blocks))
    return state.stage_index, counts, geometry


def _prune(states, items, beam_width):
    states.sort(key=lambda state: state.score, reverse=True)
    chosen, signatures = [], set()
    groups = {}
    # First preserve different stage/fulfilled-SKU/last-SKU branches.
    for state in states:
        mask = tuple(state.counts.get(item.sku, 0) >= legal_min_quantity(item) for item in items)
        last_sku = state.blocks[-1][0]["sku"] if state.blocks else ""
        group = (state.stage_index, mask, last_sku)
        if groups.get(group, 0) >= 2:
            continue
        signature = _signature(state, items)
        if signature in signatures:
            continue
        chosen.append(state)
        signatures.add(signature)
        groups[group] = groups.get(group, 0)+1
        if len(chosen) >= beam_width:
            return chosen
    for state in states:
        signature = _signature(state, items)
        if signature not in signatures:
            chosen.append(state)
            signatures.add(signature)
        if len(chosen) >= beam_width:
            break
    return chosen


def beam_pack_solutions(items, quantity, container, block_defs, beam_width=24, max_block_placements=60,
                        min_support_ratio=0.8, initial_states=None, mode="THEORETICAL_MAX", archive_limit=30,
                        deadline=None):
    """Flexible-quantity multi-SKU EMS beam search.

    `quantity` is a per-SKU ceiling. The returned final quantities are decided
    by feasible 3D placements and need not equal that ceiling.
    """
    # The first-version tool has one unified staged loading model.  Keep the
    # legacy mode labels for API/UI compatibility, but both use the same
    # physically executable sequence rules.
    realistic = True
    all_stages = sorted({item.effective_loading_stage for item in items}) if realistic else [1]
    item_by_sku = {item.sku: item for item in items}
    _state_score.container = container
    if initial_states:
        states = initial_states
    else:
        states = [SearchState(counts={item.sku: 0 for item in items}, empty_spaces=initial_space(container))]
    for state in states:
        if realistic:
            state.stage_index = min(state.stage_index, len(all_stages)-1)
        state.score = _state_score(state, items, all_stages, realistic)
    archive = [state for state in states if quantity_is_valid(state.counts, items, container)]
    hard_limit = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm

    for _ in range(max_block_placements):
        if deadline is not None and time.perf_counter() >= deadline:
            break
        next_states = []
        for state in states:
            if deadline is not None and time.perf_counter() >= deadline:
                break
            if realistic:
                stage = all_stages[state.stage_index]
                stage_items = [item for item in items if item.effective_loading_stage == stage]
                stage_minimum_met = all(state.counts.get(item.sku, 0) >= legal_min_quantity(item) for item in stage_items)
                if stage_minimum_met and state.stage_index < len(all_stages)-1:
                    transitioned = SearchState(blocks=state.blocks, counts=state.counts, empty_spaces=state.empty_spaces,
                                               volume=state.volume, weight=state.weight, stage_index=state.stage_index+1)
                    transitioned.score = _state_score(transitioned, items, all_stages, realistic)
                    next_states.append(transitioned)
                stage_deficits = [
                    item for item in stage_items
                    if state.counts.get(item.sku, 0) < legal_min_quantity(item)
                ]
                eligible_items = stage_deficits or stage_items
            for block, (x, y, z), _, _ in _moves(
                    state, eligible_items, quantity, container, min_support_ratio,
                    max(48, beam_width*6), realistic, all_items=items):
                if state.weight + block["weight_kg"] > container.max_payload + 1e-9:
                    continue
                if state.volume + block["volume_m3"] > hard_limit + 1e-9:
                    continue
                item = item_by_sku[block["sku"]]
                new_count = state.counts.get(item.sku, 0) + block["box_count"]
                if new_count > legal_max_quantity(item, container):
                    continue
                spaces = subtract_placement(
                    state.empty_spaces, x, y, z, block["length"], block["width"], block["height"],
                    clearance_mm=getattr(container, "clearance_mm_int", 0),
                )
                child = SearchState(blocks=state.blocks+[(block, (x, y, z))], counts=state.counts.copy(),
                                    empty_spaces=spaces, volume=state.volume+block["volume_m3"],
                                    weight=state.weight+block["weight_kg"], stage_index=state.stage_index)
                child.counts[item.sku] = new_count
                child.score = _state_score(child, items, all_stages, realistic)
                next_states.append(child)
                if quantity_is_valid(child.counts, items, container):
                    archive.append(child)
        if not next_states:
            break
        states = _prune(next_states, items, beam_width)
        if len(archive) > archive_limit*8:
            archive = sorted(archive, key=lambda state: state.volume, reverse=True)[:archive_limit*4]

    valid = [state for state in archive+states if quantity_is_valid(state.counts, items, container)]
    unique = {}
    for state in sorted(valid, key=lambda value: value.volume, reverse=True):
        unique.setdefault(_signature(state, items), state)
        if len(unique) >= archive_limit:
            break
    if unique:
        return list(unique.values())
    return []


def complete_state(state, items, quantity, container, min_support_ratio=0.8,
                   mode="THEORETICAL_MAX", max_additions=500, move_validator=None):
    """Greedily fill every remaining EMS with legal small blocks until stable."""
    realistic = True
    item_by_sku = {item.sku: item for item in items}
    completed = SearchState(
        blocks=list(state.blocks), counts=state.counts.copy(), empty_spaces=list(state.empty_spaces),
        volume=state.volume, weight=state.weight, stage_index=state.stage_index,
    )
    hard_limit = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm
    highest_stage = max((item.effective_loading_stage for item in items), default=1)
    additions = 0
    while additions < max_additions:
        eligible_items = [
            item for item in items
            if completed.counts.get(item.sku, 0) < min(quantity.get(item.sku, legal_max_quantity(item, container)),
                                                        legal_max_quantity(item, container))
            and (not realistic or item.effective_loading_stage == highest_stage)
        ]
        if not eligible_items:
            break
        moves = _moves(completed, eligible_items, quantity, container, min_support_ratio,
                       limit=max(4096, len(eligible_items)*1024), realistic=realistic, filler_only=True,
                       all_items=items)
        legal_moves = []
        for move in moves:
            block = move[0]
            item = item_by_sku[block["sku"]]
            new_count = completed.counts.get(item.sku, 0)+block["box_count"]
            if new_count % item.quantity_step:
                continue
            if completed.weight+block["weight_kg"] > container.max_payload+1e-9:
                continue
            if completed.volume+block["volume_m3"] > hard_limit+1e-9:
                continue
            legal_moves.append(move)
        if not legal_moves:
            break
        # Prefer volume, then tight fit; every iteration recomputes all EMS.
        legal_moves.sort(key=lambda move: (move[0]["volume_m3"], -move[2], move[0]["box_count"]), reverse=True)
        chosen = None
        for candidate in legal_moves:
            if move_validator is None or move_validator(completed, candidate[0], candidate[1]):
                chosen = candidate
                break
        if chosen is None:
            break
        block, (x, y, z), _, _ = chosen
        completed.blocks.append((block, (x, y, z)))
        completed.counts[block["sku"]] = completed.counts.get(block["sku"], 0)+block["box_count"]
        completed.volume += block["volume_m3"]
        completed.weight += block["weight_kg"]
        completed.empty_spaces = subtract_placement(
            completed.empty_spaces, x, y, z, block["length"], block["width"], block["height"],
            clearance_mm=getattr(container, "clearance_mm_int", 0))
        additions += 1
    return completed, additions


def beam_pack(items, quantity, container, block_defs, beam_width=24, max_block_placements=60,
              min_support_ratio=0.8, initial_states=None, mode="THEORETICAL_MAX"):
    """Backward-compatible single-best solver interface."""
    solutions = beam_pack_solutions(items, quantity, container, block_defs, beam_width,
                                    max_block_placements, min_support_ratio, initial_states, mode, 1)
    return solutions[0] if solutions else SearchState(
        counts={item.sku: 0 for item in items}, empty_spaces=initial_space(container))
