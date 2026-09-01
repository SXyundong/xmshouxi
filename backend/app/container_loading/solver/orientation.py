from itertools import permutations


def orientations(item) -> list[tuple[int, tuple[int, int, int]]]:
    """Return unique L/W/H permutations, respecting allowed orientation ids."""
    if not item.allow_rotation:
        all_orientations = [(0, item.dimensions_mm)]
    else:
        seen: set[tuple[int, int, int]] = set()
        all_orientations = []
        for idx, dims in enumerate(permutations(item.dimensions_mm)):
            if dims not in seen:
                seen.add(dims)
                all_orientations.append((idx, dims))
    if item.allowed_orientations is not None:
        allowed = set(item.allowed_orientations)
        all_orientations = [o for o in all_orientations if o[0] in allowed]
    return all_orientations


