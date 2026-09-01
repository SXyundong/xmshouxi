def overlaps(a, b, clearance_mm: int | float = 0) -> bool:
    """Return true when two boxes overlap or violate lateral clearance.

    Clearance is intentionally applied in X/Y only.  Boxes may touch in Z so
    that a carton can be supported by the carton below it; a non-zero vertical
    separation would make ordinary stacking impossible without dunnage.
    """
    clearance = max(0, float(clearance_mm))
    return (a.x < b.x + b.length + clearance and a.x + a.length + clearance > b.x and
            a.y < b.y + b.width + clearance and a.y + a.width + clearance > b.y and
            a.z < b.z + b.height and a.z + a.height > b.z)


def within(x, y, z, l, w, h, container) -> bool:
    cl, cw, ch = container.dimensions_mm
    return x >= 0 and y >= 0 and z >= 0 and x+l <= cl and y+w <= cw and z+h <= ch


def support_ratio(x, y, z, l, w, placed) -> float:
    if z == 0:
        return 1.0
    rectangles = []
    for p in placed:
        if p.z + p.height != z:
            continue
        x1, x2 = max(x, p.x), min(x+l, p.x+p.length)
        y1, y2 = max(y, p.y), min(y+w, p.y+p.width)
        if x1 < x2 and y1 < y2:
            rectangles.append((x1, x2, y1, y2))
    if not rectangles:
        return 0.0
    xs = sorted({coordinate for rectangle in rectangles for coordinate in rectangle[:2]})
    area = 0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((y1, y2) for x1, x2, y1, y2 in rectangles if x1 <= left and x2 >= right)
        covered = 0
        if intervals:
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start > end:
                    covered += end-start
                    start, end = next_start, next_end
                else:
                    end = max(end, next_end)
            covered += end-start
        area += (right-left) * covered
    return min(1.0, area / max(1, l*w))


def validate_placements(placements, container, max_payload: float, min_support_ratio: float = 0.8):
    clearance = getattr(container, "clearance_mm_int", 0)
    no_overlap = all(not overlaps(a, b, clearance) for i, a in enumerate(placements) for b in placements[i+1:])
    in_bounds = all(within(p.x, p.y, p.z, p.length, p.width, p.height, container) for p in placements)
    weight_ok = sum(p.weight_kg for p in placements) <= max_payload + 1e-9
    supported = all(support_ratio(p.x, p.y, p.z, p.length, p.width, placements[:i]) + 1e-9 >= min_support_ratio
                    for i, p in enumerate(placements))
    return {"no_overlap": no_overlap, "within_container": in_bounds, "weight_ok": weight_ok, "supported": supported,
            "valid": no_overlap and in_bounds and weight_ok and supported}


