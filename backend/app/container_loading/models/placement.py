from pydantic import BaseModel


class Placement(BaseModel):
    box_id: str
    sku: str
    factory: str | None = None
    x: int
    y: int
    z: int
    length: int
    width: int
    height: int
    orientation: int
    weight_kg: float
    loading_stage: int = 1
    block_id: str | None = None


