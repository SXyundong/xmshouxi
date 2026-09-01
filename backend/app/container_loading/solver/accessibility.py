from __future__ import annotations

from .geometry import overlaps


def swept_path_clear(x: int, y: int, z: int, length: int, width: int, height: int,
                     occupied, container) -> bool:
    """Axis-aligned insertion from the door at x=container_length.

    Touching the target's rear face is allowed. Any already loaded object whose
    volume intersects the open corridor between that face and the door blocks
    insertion. This intentionally models a practical straight push, not robot
    motion planning.
    """
    container_length, _, _ = container.dimensions_mm
    corridor_start = x + length
    if corridor_start >= container_length:
        return True
    corridor = type("Corridor", (), {
        "x": corridor_start, "y": y, "z": z,
        "length": container_length - corridor_start,
        "width": width, "height": height,
    })()
    return not any(overlaps(corridor, placed, getattr(container, "clearance_mm_int", 0)) for placed in occupied)


def validate_accessibility(placements, container) -> dict[str, bool]:
    occupied = []
    stage_ordered = True
    last_stage = 0
    accessible = True
    for placement in placements:
        stage = placement.loading_stage
        if stage < last_stage:
            stage_ordered = False
        last_stage = max(last_stage, stage)
        if not swept_path_clear(placement.x, placement.y, placement.z, placement.length,
                                placement.width, placement.height, occupied, container):
            accessible = False
            break
        occupied.append(placement)
    return {
        "factory_sequence_valid": stage_ordered,
        "accessibility_valid": accessible,
        "sequence_valid": stage_ordered and accessible,
    }


