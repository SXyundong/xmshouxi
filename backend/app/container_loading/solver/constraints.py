from __future__ import annotations

from collections import defaultdict

from .geometry import overlaps, support_ratio, within
from .orientation import orientations
from .quantity_optimizer import quantity_is_valid


def _overlap_area_xy(a, b) -> int:
    x = max(0, min(a.x+a.length, b.x+b.length)-max(a.x, b.x))
    y = max(0, min(a.y+a.width, b.y+b.width)-max(a.y, b.y))
    return x*y


def _support_graph(placements):
    """Return direct supporters and support-chain depth for every carton."""
    by_top = defaultdict(list)
    for index, placement in enumerate(placements):
        by_top[placement.z+placement.height].append((index, placement))
    supporters: dict[int, list[tuple[int, int]]] = {}
    depths = [1]*len(placements)
    for index in sorted(range(len(placements)), key=lambda i: placements[i].z):
        placement = placements[index]
        direct = []
        if placement.z > 0:
            for lower_index, lower in by_top.get(placement.z, []):
                area = _overlap_area_xy(placement, lower)
                if area:
                    direct.append((lower_index, area))
        supporters[index] = direct
        if direct:
            depths[index] = 1+max(depths[lower_index] for lower_index, _ in direct)
    return supporters, depths


def _stack_and_load_validation(placements, item_by_sku):
    supporters, depths = _support_graph(placements)
    stack_limit_ok = True
    for index, placement in enumerate(placements):
        limit = item_by_sku[placement.sku].stack_limit
        if limit is not None and depths[index] > limit:
            stack_limit_ok = False
            break

    # Each carton transfers its own weight plus accumulated top load to direct
    # supporters in proportion to overlap area.
    top_load = [0.0]*len(placements)
    for index in sorted(range(len(placements)), key=lambda i: placements[i].z, reverse=True):
        direct = supporters[index]
        if not direct:
            continue
        transferable = placements[index].weight_kg+top_load[index]
        total_area = sum(area for _, area in direct)
        if total_area:
            for lower_index, area in direct:
                top_load[lower_index] += transferable*area/total_area

    top_load_ok = True
    fragile_ok = True
    for index, placement in enumerate(placements):
        item = item_by_sku[placement.sku]
        if item.max_top_load_kg is not None and top_load[index] > item.max_top_load_kg+1e-9:
            top_load_ok = False
        if item.fragile and top_load[index] > 1e-9:
            fragile_ok = False
    return stack_limit_ok, top_load_ok, fragile_ok, top_load


def _orientation_validation(placements, item_by_sku):
    for placement in placements:
        legal = {identifier: dims for identifier, dims in orientations(item_by_sku[placement.sku])}
        if legal.get(placement.orientation) != (placement.length, placement.width, placement.height):
            return False
    return True


def _door_validation(placements, container):
    if container.door_width is None or container.door_height is None:
        return True
    door_width = round(container.door_width*10)
    door_height = round(container.door_height*10)
    clearance = getattr(container, "clearance_mm_int", 0)
    return all(placement.width + 2*clearance <= door_width and placement.height <= door_height
               for placement in placements)


def _stage_layout_validation(placements, items, container):
    """Ensure factory stages occupy consecutive head-to-door X bands."""
    if not placements:
        return True
    item_by_sku = {item.sku: item for item in items}
    by_stage = defaultdict(list)
    for placement in placements:
        by_stage[item_by_sku[placement.sku].effective_loading_stage].append(placement)
    clearance = getattr(container, "clearance_mm_int", 0)
    previous_end = 0
    for stage in sorted(by_stage):
        current = by_stage[stage]
        current_start = min(placement.x for placement in current)
        if current_start < previous_end:
            return False
        previous_end = max(placement.x + placement.length for placement in current) + clearance
    return True


def validate_solution(placements, container, items, mode, min_support_ratio=0.8):
    """Independent carton-level validation; never trusts the search state."""
    item_by_sku = {item.sku: item for item in items}
    clearance = getattr(container, "clearance_mm_int", 0)
    no_overlap = all(not overlaps(a, b, clearance) for index, a in enumerate(placements) for b in placements[index+1:])
    in_bounds = all(within(p.x, p.y, p.z, p.length, p.width, p.height, container) for p in placements)
    weight_ok = sum(p.weight_kg for p in placements) <= container.max_payload+1e-9
    supported = all(
        support_ratio(p.x, p.y, p.z, p.length, p.width, placements[:index])+1e-9 >= min_support_ratio
        for index, p in enumerate(placements)
    )
    orientation_ok = _orientation_validation(placements, item_by_sku)
    quantities = {item.sku: 0 for item in items}
    for placement in placements:
        quantities[placement.sku] += 1
    quantity_ok = quantity_is_valid(quantities, items, container)
    stack_limit_ok, top_load_ok, fragile_ok, top_load = _stack_and_load_validation(placements, item_by_sku)
    # Both legacy result labels now represent the same physically executable
    # staged model.
    realistic = True
    door_ok = _door_validation(placements, container) if realistic else True
    stage_layout_ok = _stage_layout_validation(placements, items, container)
    validation = {
        "no_overlap": no_overlap,
        "within_container": in_bounds,
        "weight_ok": weight_ok,
        "supported": supported,
        "legal_orientations": orientation_ok,
        "quantity_constraints": quantity_ok,
        "door_valid": door_ok,
        "stack_limit_valid": stack_limit_ok,
        "top_load_valid": top_load_ok,
        "fragile_valid": fragile_ok,
        "stage_layout_valid": stage_layout_ok,
    }
    validation["valid"] = all(validation.values())
    return validation, quantities, top_load
