from pydantic import BaseModel


class Block(BaseModel):
    block_id: str
    sku: str
    nx: int
    ny: int
    nz: int
    box_count: int
    x: int
    y: int
    z: int
    length: int
    width: int
    height: int
    orientation: int
    weight_kg: float
    volume_m3: float
    loading_stage: int = 1


