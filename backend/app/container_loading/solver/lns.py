from __future__ import annotations

from .beam_search import SearchState
from .maximal_spaces import spaces_after_blocks


def _state_from_kept(state, kept, items, container, stage_index=None):
    counts = {item.sku: 0 for item in items}
    volume = weight = 0.0
    for block, _ in kept:
        counts[block["sku"]] += block["box_count"]
        volume += block["volume_m3"]
        weight += block["weight_kg"]
    return SearchState(
        blocks=list(kept), counts=counts, empty_spaces=spaces_after_blocks(container, kept),
        volume=volume, weight=weight,
        stage_index=state.stage_index if stage_index is None else stage_index,
        stack_move_count=state.stack_move_count,
    )


def destroy_states(state, items, container, mode, max_variants=8):
    """Create deterministic large neighbourhoods for destroy-and-repair."""
    if len(state.blocks) < 2:
        return []
    # Legacy mode names are retained by the API, but the first version uses
    # the same staged physical loading model for every result.
    realistic = True
    variants = []
    if realistic:
        # Only destroy a loading-sequence suffix; earlier frozen cargo remains
        # executable and the removed final stage can be repaired.
        for fraction in (0.15, 0.25, 0.35):
            count = max(1, round(len(state.blocks)*fraction))
            kept = state.blocks[:-count]
            stages = sorted({item.effective_loading_stage for item in items})
            last_stage = max((next(i.effective_loading_stage for i in items if i.sku == block["sku"])
                              for block, _ in kept), default=stages[0])
            variants.append(_state_from_kept(state, kept, items, container, stages.index(last_stage)))
    else:
        count_options = {max(1, round(len(state.blocks)*fraction)) for fraction in (0.10, 0.20, 0.30)}
        for count in sorted(count_options):
            variants.append(_state_from_kept(state, state.blocks[:-count], items, container))
        # Spatial neighbourhoods: door end and highest fragmented blocks.
        by_door = sorted(state.blocks, key=lambda entry: entry[1][0]+entry[0]["length"], reverse=True)
        by_top = sorted(state.blocks, key=lambda entry: entry[1][2]+entry[0]["height"], reverse=True)
        remove_count = max(1, len(state.blocks)//4)
        for ordered in (by_door, by_top):
            removed = {id(entry) for entry in ordered[:remove_count]}
            kept = [entry for entry in state.blocks if id(entry) not in removed]
            variants.append(_state_from_kept(state, kept, items, container))
    unique = {}
    for variant in variants:
        signature = tuple((block["sku"], position) for block, position in variant.blocks)
        unique.setdefault(signature, variant)
        if len(unique) >= max_variants:
            break
    return list(unique.values())
