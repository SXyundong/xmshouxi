from ..models.block import Block
from .orientation import orientations


def _axis_capacity(total: int, unit: int, clearance: int) -> int:
    """Maximum count of units with a lateral gap between neighbouring units."""
    if unit <= 0 or total < unit:
        return 0
    return max(0, (total + clearance) // (unit + clearance))


def _axis_size(count: int, unit: int, clearance: int) -> int:
    return count * unit + max(0, count - 1) * clearance


def _vertical_limit(item, geometric_limit: int) -> int:
    limit = geometric_limit
    if item.stack_limit is not None:
        limit = min(limit, item.stack_limit)
    if item.fragile:
        limit = min(limit, 1)
    if item.max_top_load_kg is not None and item.carton_weight_kg > 0:
        limit = min(limit, int(item.max_top_load_kg//item.carton_weight_kg)+1)
    return limit


def _axis_counts(max_count: int) -> list[int]:
    """Keep all practical counts while bounding pathological tiny-carton cases."""
    if max_count <= 30:
        return list(range(1, max_count + 1))
    values = {1, 2, 3, 4, 5, 6, 8, 10, max_count}
    values.update({max_count // 4, max_count // 3, max_count // 2, 2 * max_count // 3,
                   3 * max_count // 4, max_count - 2, max_count - 1})
    return sorted(v for v in values if 1 <= v <= max_count)


def _space_axis_counts(max_nx: int, max_ny: int, max_nz: int, remaining: int,
                       filler_only: bool = False) -> tuple[set[int], set[int], set[int], set[tuple[int, int, int]]]:
    """Return axis counts that include cross-section-first exact fits.

    Sampling only ``1 / half / max`` on each axis misses useful layouts such
    as 200 cartons arranged as 20 x 2 x 5.  The old sampler therefore tends
    to choose a 10 metre long, two-carton-wide wall even when the same count
    can be packed in a much shorter, wider block.  For every Y/Z cross-section
    we explicitly add the largest legal X count, which also preserves exact
    divisors of the remaining fixed quantity.
    """
    x_values = {1, max_nx, max(1, max_nx // 2), max(1, max_nx - 1)}
    y_values = {1, max_ny, max(1, max_ny // 2), max(1, max_ny - 1)}
    z_values = {1, max_nz, max(1, max_nz // 2), max(1, max_nz - 1)}
    cross_section_counts = set()
    if filler_only:
        x_values.update(range(1, min(max_nx, 4) + 1))
        y_values.update(range(1, min(max_ny, 4) + 1))
        z_values.update(range(1, min(max_nz, 4) + 1))

    for ny in range(1, max_ny + 1):
        for nz in range(1, max_nz + 1):
            layer = ny * nz
            if layer <= remaining:
                largest_x = min(max_nx, max(1, remaining // layer))
                cross_section_counts.add((largest_x, ny, nz))
                # Keep the nearest lower count as a separate candidate when
                # the exact remaining quantity cannot fill a whole layer.
                lower_x = min(max_nx, max(1, (remaining - 1) // layer))
                cross_section_counts.add((lower_x, ny, nz))
    return (
        {value for value in x_values if 1 <= value <= max_nx},
        {value for value in y_values if 1 <= value <= max_ny},
        {value for value in z_values if 1 <= value <= max_nz},
        cross_section_counts,
    )


def generate_blocks(item, container, max_candidates: int = 80) -> list[dict]:
    """Generate useful tight homogeneous blocks for one SKU."""
    cl, cw, ch = container.dimensions_mm
    clearance = getattr(container, "clearance_mm_int", 0)
    max_qty = item.max_quantity if item.max_quantity is not None else max(
        1, int(cl * cw * ch / max(1, item.dimensions_mm[0] * item.dimensions_mm[1] * item.dimensions_mm[2])))
    if max_qty == 0:
        return []
    result: list[dict] = []
    seen = set()
    for orientation, (l, w, h) in orientations(item):
        if l > cl or w > cw or h > ch:
            continue
        max_nx, max_ny, max_nz = _axis_capacity(cl, l, clearance), _axis_capacity(cw, w, clearance), ch // h
        max_nz = _vertical_limit(item, max_nz)
        for nx in _axis_counts(max_nx):
            for ny in _axis_counts(max_ny):
                for nz in _axis_counts(max_nz):
                    count = nx * ny * nz
                    if count > max_qty:
                        continue
                    key = (orientation, nx, ny, nz)
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append({"sku": item.sku, "nx": nx, "ny": ny, "nz": nz,
                                   "box_count": count, "length": _axis_size(nx, l, clearance),
                                   "width": _axis_size(ny, w, clearance), "height": nz*h,
                                   "unit_length": l, "unit_width": w, "unit_height": h,
                                   "orientation": orientation, "weight_kg": count*item.carton_weight_kg,
                                   "volume_m3": count*item.volume_m3})
    # Keep high-capacity blocks, partial-cross-section shapes, and small fillers.
    result.sort(key=lambda b: (b["box_count"], b["length"]*b["width"]*b["height"]), reverse=True)
    filler_slots = min(12, max(0, max_candidates // 4))
    slab_slots = min(24, max(0, max_candidates // 3))
    selected = result[:max(0, max_candidates - filler_slots - slab_slots - 12)]
    slabs = []
    for orientation, (l, w, h) in orientations(item):
        max_ny, max_nz = _axis_capacity(cw, w, clearance), ch // h
        slabs.extend(b for b in result if b["orientation"] == orientation and b["ny"] == max_ny and b["nz"] == max_nz)
    slabs.sort(key=lambda b: b["box_count"], reverse=True)
    for b in slabs[:slab_slots]:
        if b not in selected:
            selected.append(b)
    if result:
        for b in sorted(result, key=lambda x: x["box_count"]):
            if b not in selected and b["box_count"] in {1, 2, 4, 8, 16, 32}:
                selected.append(b)
    # Explicitly preserve narrow and low blocks. Without these, a global volume
    # sort silently turns EMS search back into full-cross-section slab packing.
    for selector in (
        lambda b: (b["width"], -b["volume_m3"]),
        lambda b: (b["height"], -b["volume_m3"]),
        lambda b: (b["width"]*b["height"], -b["volume_m3"]),
    ):
        for b in sorted(result, key=selector)[:4]:
            if b not in selected:
                selected.append(b)
    # Filler blocks are useful, but never allow them to defeat the candidate cap.
    return selected[:max_candidates]


def generate_blocks_for_space(item, space, remaining: int, max_candidates: int = 24,
                              filler_only: bool = False, clearance_mm: int | float = 0) -> list[dict]:
    """Generate blocks after seeing the actual EMS dimensions.

    Every legal single-carton orientation is retained. Larger shapes are
    sampled per axis and ranked only after they are known to fit this space.
    """
    if remaining <= 0:
        return []
    result = []
    for orientation, (l, w, h) in orientations(item):
        clearance = max(0, round(float(clearance_mm)))
        max_nx, max_ny, max_nz = _axis_capacity(space.length, l, clearance), _axis_capacity(space.width, w, clearance), space.height//h
        max_nz = _vertical_limit(item, max_nz)
        if min(max_nx, max_ny, max_nz) <= 0:
            continue
        max_nx = min(max_nx, remaining)
        x_values, y_values, z_values, cross_section_counts = _space_axis_counts(
            max_nx, max_ny, max_nz, remaining, filler_only
        )
        count_triples = {(nx, ny, nz) for nx in x_values for ny in y_values for nz in z_values}
        count_triples.update(cross_section_counts)
        # ``count_triples`` is a set assembled from sampled axis counts and
        # exact cross-section counts.  Iterating it directly makes candidate
        # order depend on hash randomisation, which changes beam pruning and
        # can produce different quantities for identical inputs.
        for nx, ny, nz in sorted(count_triples):
            count = nx*ny*nz
            if count > remaining or (filler_only and count > 16):
                continue
            result.append({
                "sku": item.sku, "nx": nx, "ny": ny, "nz": nz, "box_count": count,
                "length": _axis_size(nx, l, clearance), "width": _axis_size(ny, w, clearance),
                "height": nz*h, "unit_length": l, "unit_width": w, "unit_height": h,
                "orientation": orientation,
                "weight_kg": count*item.carton_weight_kg, "volume_m3": count*item.volume_m3,
            })
    unique = {}
    for block in result:
        key = (block["orientation"], block["nx"], block["ny"], block["nz"])
        unique.setdefault(key, block)
    blocks = list(unique.values())
    singles = [block for block in blocks if block["box_count"] == 1]
    others = [block for block in blocks if block["box_count"] != 1]
    others.sort(key=lambda block: (
        block["volume_m3"],
        block["length"]*block["width"]*block["height"]/(space.volume or 1),
        -block["box_count"],
    ), reverse=True)
    if filler_only:
        # Completion is a correctness pass: no small shape may disappear due
        # to a global candidate cap.
        return singles+others
    selected = list(singles)
    # Preserve shape diversity, not just the largest count.
    buckets = set()
    for block in others:
        bucket = (
            min(3, block["length"]*4//max(1, space.length)),
            min(3, block["width"]*4//max(1, space.width)),
            min(3, block["height"]*4//max(1, space.height)),
        )
        if bucket not in buckets or len(selected) < max_candidates//2:
            selected.append(block)
            buckets.add(bucket)
        if len(selected) >= max_candidates:
            break
    return selected[:max_candidates]
