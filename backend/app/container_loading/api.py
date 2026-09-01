"""Agent-facing APIs for the native logistics container-loading tool."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from app.core.auth import current_identity

from .jobs import container_loading_jobs
from .models.container import Container
from .product_service import lookup_products, resolve_items

router = APIRouter(prefix="/api/tools/logistics/container-loading", tags=["container-loading"])


class ProductLookupResponse(BaseModel):
    identifier: str
    candidates: list[dict]


class ContainerLoadingItemRequest(BaseModel):
    product_market_parameter_id: UUID
    min_quantity: int = Field(default=0, ge=0)
    max_quantity: int | None = Field(default=None, ge=0)
    quantity_step: int = Field(default=1, gt=0)
    loading_stage: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            raise ValueError("最高整箱数不能小于最低整箱数")
        return self


class ContainerLoadingJobRequest(BaseModel):
    items: list[ContainerLoadingItemRequest] = Field(min_length=1)
    container: Container = Field(default_factory=Container)


class ContainerLoadingItemInfo(BaseModel):
    product_market_parameter_id: UUID
    solver_sku: str
    sku: str
    msku: str | None = None
    product_name: str | None = None
    country: str
    store: str | None = None
    carton_length_cm: float
    carton_width_cm: float
    carton_height_cm: float
    carton_weight_kg: float
    min_quantity: int
    max_quantity: int | None
    quantity_step: int
    loading_stage: int


class ContainerLoadingJobResponse(BaseModel):
    status: Literal["queued", "running", "complete", "failed"]
    job_id: str
    progress: int
    message: str
    error: str = ""
    items: list[ContainerLoadingItemInfo] = []
    results: dict | None = None


def _job_response(job) -> ContainerLoadingJobResponse:
    infos = []
    for item in job.resolved:
        product = item.product
        infos.append(
            ContainerLoadingItemInfo(
                product_market_parameter_id=product.id,
                solver_sku=item.solver_sku,
                sku=product.sku,
                msku=product.amazon_sku,
                product_name=product.product_name or product.name_zh or product.name_en,
                country=product.market.name if product.market else product.country_code,
                store=product.store,
                carton_length_cm=float(product.carton_length_cm),
                carton_width_cm=float(product.carton_width_cm),
                carton_height_cm=float(product.carton_height_cm),
                carton_weight_kg=float(product.carton_weight_kg),
                min_quantity=item.min_quantity,
                max_quantity=item.max_quantity,
                quantity_step=item.quantity_step,
                loading_stage=item.loading_stage,
            )
        )
    return ContainerLoadingJobResponse(
        status=job.status,
        job_id=job.job_id,
        progress=job.progress,
        message=job.message,
        error=job.error,
        items=infos,
        results=job.results,
    )


@router.get("/products", response_model=ProductLookupResponse)
def products(request: Request, identifier: str = Query(min_length=1, max_length=100)):
    current_identity(request)
    normalized = identifier.strip().upper()
    return ProductLookupResponse(identifier=normalized, candidates=lookup_products(normalized))


@router.post("/jobs", response_model=ContainerLoadingJobResponse)
def start_job(request: Request, body: ContainerLoadingJobRequest):
    identity = current_identity(request)
    try:
        resolved = resolve_items([item.model_dump(mode="json") for item in body.items])
        job = container_loading_jobs.create(identity["open_id"], body.container, resolved)
        return _job_response(job)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=ContainerLoadingJobResponse)
def job_status(request: Request, job_id: str):
    identity = current_identity(request)
    job = container_loading_jobs.get(job_id, identity["open_id"])
    if job is None:
        raise HTTPException(status_code=404, detail="装柜任务不存在或无权访问")
    return _job_response(job)
