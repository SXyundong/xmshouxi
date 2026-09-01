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
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            raise ValueError("max_quantity must be >= min_quantity")
        if self.max_quantity is not None:
            first_legal = ((self.min_quantity + self.quantity_step - 1) // self.quantity_step) * self.quantity_step
            if first_legal > self.max_quantity:
                raise ValueError("quantity range contains no value compatible with quantity_step")
        return self

    @property
    def effective_loading_stage(self) -> int:
        return self.loading_stage if self.loading_stage is not None else self.factory_sequence

    @property
    def dimensions_mm(self) -> tuple[int, int, int]:
        return tuple(round(v * 10) for v in (self.carton_length_cm, self.carton_width_cm, self.carton_height_cm))

    @property
    def volume_m3(self) -> float:
        return self.carton_length_cm * self.carton_width_cm * self.carton_height_cm / 1_000_000


