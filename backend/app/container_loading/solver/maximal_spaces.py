from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmptySpace:
    x: int
    y: int
    z: int
    length: int
    width: int
    height: int

    @property
    def volume(self) -> int:
        return self.length * self.width * self.height

    def contains(self, other: "EmptySpace") -> bool:
        return (self.x <= other.x and self.y <= other.y and self.z <= other.z and
                self.x + self.length >= other.x + other.length and
                self.y + self.width >= other.y + other.width and
                self.z + self.height >= other.z + other.height)


def _intersects(space: EmptySpace, x: int, y: int, z: int, length: int, width: int, height: int) -> bool:
    return (space.x < x + length and space.x + space.length > x and
            space.y < y + width and space.y + space.width > y and
            space.z < z + height and space.z + space.height > z)


def prune_spaces(spaces: list[EmptySpace], minimum_dimensions: list[tuple[int, int, int]] | None = None) -> list[EmptySpace]:
    unique = list(dict.fromkeys(s for s in spaces if s.length > 0 and s.width > 0 and s.height > 0))
    if minimum_dimensions:
        unique = [s for s in unique if any(l <= s.length and w <= s.width and h <= s.height
                                           for l, w, h in minimum_dimensions)]
    unique.sort(key=lambda s: s.volume, reverse=True)
    kept: list[EmptySpace] = []
    for candidate in unique:
        if not any(existing.contains(candidate) for existing in kept):
            kept.append(candidate)
    return kept


def subtract_placement(spaces: list[EmptySpace], x: int, y: int, z: int, length: int, width: int, height: int,
                       minimum_dimensions: list[tuple[int, int, int]] | None = None,
                       clearance_mm: int | float = 0) -> list[EmptySpace]:
    """Split every intersected EMS around an axis-aligned placement."""
    split: list[EmptySpace] = []
    clearance = max(0, round(float(clearance_mm)))
    for space in spaces:
        # Reserve the requested lateral handling gap around each placement.
        # Clamp the safety rectangle to the EMS so boundary-touching cartons
        # remain legal while neighbouring cartons cannot be placed too close.
        safe_x = max(space.x, x - clearance)
        safe_y = max(space.y, y - clearance)
        safe_x2 = min(space.x + space.length, x + length + clearance)
        safe_y2 = min(space.y + space.width, y + width + clearance)
        safe_length, safe_width = safe_x2-safe_x, safe_y2-safe_y
        if safe_length <= 0 or safe_width <= 0 or not _intersects(space, safe_x, safe_y, z, safe_length, safe_width, height):
            split.append(space)
            continue
        sx2, sy2, sz2 = space.x + space.length, space.y + space.width, space.z + space.height
        # Six maximal slabs. They may overlap; containment pruning and final
        # collision checks keep placement correctness while preserving options.
        if safe_x > space.x:
            split.append(EmptySpace(space.x, space.y, space.z, safe_x-space.x, space.width, space.height))
        if safe_x2 < sx2:
            split.append(EmptySpace(safe_x2, space.y, space.z, sx2-safe_x2, space.width, space.height))
        if safe_y > space.y:
            split.append(EmptySpace(space.x, space.y, space.z, space.length, safe_y-space.y, space.height))
        if safe_y2 < sy2:
            split.append(EmptySpace(space.x, safe_y2, space.z, space.length, sy2-safe_y2, space.height))
        if z > space.z:
            split.append(EmptySpace(space.x, space.y, space.z, space.length, space.width, z-space.z))
        pz2 = z + height
        if pz2 < sz2:
            split.append(EmptySpace(space.x, space.y, pz2, space.length, space.width, sz2-pz2))
    return prune_spaces(split, minimum_dimensions)


def initial_space(container) -> list[EmptySpace]:
    length, width, height = container.dimensions_mm
    return [EmptySpace(0, 0, 0, length, width, height)]


def spaces_after_blocks(container, blocks) -> list[EmptySpace]:
    spaces = initial_space(container)
    for definition, (x, y, z) in blocks:
        spaces = subtract_placement(spaces, x, y, z, definition["length"], definition["width"], definition["height"],
                                     clearance_mm=getattr(container, "clearance_mm_int", 0))
    return spaces


