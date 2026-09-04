from typing import Literal
from pydantic import BaseModel, Field


class Container(BaseModel):
    """Container dimensions are supplied in centimetres and converted to mm internally."""

    container_length: float = Field(1203.2, gt=0)
    container_width: float = Field(235.2, gt=0)
    container_height: float = Field(269.0, gt=0)
    door_width: float | None = Field(234.0, gt=0)
    door_height: float | None = Field(258.0, gt=0)
    max_payload: float = Field(26500.0, gt=0)
    operational_target_cbm: float = Field(68.0, gt=0)
    operational_mode: Literal["target", "soft_limit", "hard_limit"] = "target"
    # V0.9 physical lateral (Y-axis) free distance between adjacent cartons.
    # X face contact and vertical stacking contact remain allowed.
    clearance_mm: float = Field(0.0, ge=0, le=100)

    @property
    def dimensions_mm(self) -> tuple[int, int, int]:
        return tuple(round(v * 10) for v in (self.container_length, self.container_width, self.container_height))

    @property
    def physical_cbm(self) -> float:
        return self.container_length * self.container_width * self.container_height / 1_000_000

    @property
    def clearance_mm_int(self) -> int:
        return round(self.clearance_mm)

