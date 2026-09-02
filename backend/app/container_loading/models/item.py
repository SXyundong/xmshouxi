from pydantic import BaseModel, Field, model_validator


class Item(BaseModel):
    sku: str
    carton_length_cm: float = Field(gt=0)
    carton_width_cm: float = Field(gt=0)
    carton_height_cm: float = Field(gt=0)
    carton_weight_kg: float = Field(default=0, ge=0)
    min_quantity: int = Field(default=0, ge=0)
    max_quantity: int | None = Field(default=None, ge=0)
    quantity_step: int = Field(default=1, gt=0)
    factory: str | None = None
    factory_sequence: int = Field(default=1, ge=1)
    loading_stage: int | None = Field(default=None, ge=1)
    priority: int = Field(default=1, ge=0)
    allow_rotation: bool = True
    allowed_orientations: list[int] | None = None
    stack_limit: int | None = Field(default=None, gt=0)
    max_top_load_kg: float | None = Field(default=None, ge=0)
    fragile: bool = False
    @model_validator(mode="after")
    def validate_quantities(self):
        if self.max_quantity is None:
            if self.min_quantity != 0:
                raise ValueError("自动填充商品的最低数量必须为 0")
        elif self.max_quantity != self.min_quantity:
            raise ValueError("第一版只支持固定数量或自动填充，不支持数量范围")
        elif self.min_quantity % self.quantity_step:
            raise ValueError("固定数量必须符合整箱步长")
        return self

    @property
    def is_auto_fill(self) -> bool:
        return self.max_quantity is None

    @property
    def effective_loading_stage(self) -> int:
        return self.loading_stage if self.loading_stage is not None else self.factory_sequence

    @property
    def dimensions_mm(self) -> tuple[int, int, int]:
        return tuple(round(v * 10) for v in (self.carton_length_cm, self.carton_width_cm, self.carton_height_cm))

    @property
    def volume_m3(self) -> float:
        return self.carton_length_cm * self.carton_width_cm * self.carton_height_cm / 1_000_000

