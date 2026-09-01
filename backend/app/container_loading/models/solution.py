from pydantic import BaseModel, Field
from .block import Block
from .placement import Placement


class SolutionMetrics(BaseModel):
    balance_score: float = 0.0
    fragmentation_score: float = 0.0
    loading_complexity: float = 0.0


class OptimizationResult(BaseModel):
    solution_id: str = "SOLUTION-1"
    solution_name: str = "Best volume"
    mode: str
    mix_policy: str = "FREE"
    clearance_mm: float = 0.0
    solution_status: str = "BEST_FOUND"
    locally_maximal: bool = False
    loaded_cbm: float
    physical_utilization: float
    operational_utilization: float
    total_weight_kg: float
    loaded_boxes: int
    sku_quantities: dict[str, int]
    blocks: list[Block] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)
    loading_sequence: list[dict] = Field(default_factory=list)
    metrics: SolutionMetrics = Field(default_factory=SolutionMetrics)
    upper_bound_cbm: float | None = None
    upper_bound_proven: bool = True
    optimality_gap_percent: float | None = None
    validation: dict[str, bool] = Field(default_factory=dict)
    solve_time_seconds: float = 0.0
    initial_seed_cbm: float = 0.0
    search_improvement_cbm: float = 0.0
    alternatives: list[dict] = Field(default_factory=list)


