"""Resolve container-loading inputs from canonical product master data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.db.models import ProductMarketParameter
from app.db.session import SessionLocal

from .models.item import Item


@dataclass(frozen=True)
class ResolvedProduct:
    product: ProductMarketParameter
    solver_sku: str
    min_quantity: int
    max_quantity: int | None
    quantity_step: int
    loading_stage: int


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def product_candidate(product: ProductMarketParameter) -> dict:
    carton_values = {
        "length_cm": _number(product.carton_length_cm),
        "width_cm": _number(product.carton_width_cm),
        "height_cm": _number(product.carton_height_cm),
        "weight_kg": _number(product.carton_weight_kg),
    }
    return {
        "id": str(product.id),
        "sku": product.sku,
        "msku": product.amazon_sku,
        "product_name": product.product_name or product.name_zh or product.name_en,
        "country_code": product.country_code,
        "country": product.market.name if product.market else product.country_code,
        "store": product.store,
        "carton_length_cm": carton_values["length_cm"],
        "carton_width_cm": carton_values["width_cm"],
        "carton_height_cm": carton_values["height_cm"],
        "carton_weight_kg": carton_values["weight_kg"],
        "parameters_complete": all(value is not None for value in carton_values.values()),
    }


def lookup_products(identifier: str) -> list[dict]:
    normalized = identifier.strip().upper()
    if not normalized:
        return []
    statement = (
        select(ProductMarketParameter)
        .options(joinedload(ProductMarketParameter.market))
        .where(
            ProductMarketParameter.is_active.is_(True),
            or_(
                func.upper(ProductMarketParameter.sku) == normalized,
                func.upper(ProductMarketParameter.amazon_sku) == normalized,
            ),
        )
        .order_by(
            ProductMarketParameter.sku,
            ProductMarketParameter.country_code,
            ProductMarketParameter.store,
            ProductMarketParameter.id,
        )
    )
    with SessionLocal() as session:
        products = session.scalars(statement).unique().all()
        return [product_candidate(product) for product in products]


def resolve_items(items: list[dict]) -> list[ResolvedProduct]:
    ids = [UUID(str(item["product_market_parameter_id"])) for item in items]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="同一个商品不能在同一装柜方案中重复添加")

    statement = (
        select(ProductMarketParameter)
        .options(joinedload(ProductMarketParameter.market))
        .where(ProductMarketParameter.id.in_(ids), ProductMarketParameter.is_active.is_(True))
    )
    with SessionLocal() as session:
        products = {product.id: product for product in session.scalars(statement).unique().all()}

    missing = [str(product_id) for product_id in ids if product_id not in products]
    if missing:
        raise HTTPException(status_code=422, detail=f"商品不存在或已停用：{', '.join(missing)}")

    resolved: list[ResolvedProduct] = []
    for item, product_id in zip(items, ids):
        product = products[product_id]
        dimensions = (
            product.carton_length_cm,
            product.carton_width_cm,
            product.carton_height_cm,
            product.carton_weight_kg,
        )
        if any(value is None for value in dimensions):
            raise HTTPException(
                status_code=422,
                detail=f"商品 {product.sku} 的整箱长、宽、高或重量不完整，无法计算",
            )
        if any(float(value) <= 0 for value in dimensions[:3]) or float(dimensions[3]) < 0:
            raise HTTPException(status_code=422, detail=f"商品 {product.sku} 的整箱参数无效，无法计算")

        resolved.append(
            ResolvedProduct(
                product=product,
                solver_sku=f"PRODUCT::{product.id}",
                min_quantity=int(item["min_quantity"]),
                max_quantity=item.get("max_quantity"),
                quantity_step=int(item.get("quantity_step", 1)),
                loading_stage=int(item["loading_stage"]),
            )
        )
    return resolved


def to_solver_items(resolved: list[ResolvedProduct]) -> list[Item]:
    return [
        Item(
            sku=item.solver_sku,
            carton_length_cm=float(item.product.carton_length_cm),
            carton_width_cm=float(item.product.carton_width_cm),
            carton_height_cm=float(item.product.carton_height_cm),
            carton_weight_kg=float(item.product.carton_weight_kg),
            min_quantity=item.min_quantity,
            max_quantity=item.max_quantity,
            quantity_step=item.quantity_step,
            loading_stage=item.loading_stage,
            factory=f"Stage-{item.loading_stage}",
        )
        for item in resolved
    ]
