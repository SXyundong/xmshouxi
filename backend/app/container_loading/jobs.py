"""In-process asynchronous jobs for the CPU-heavy container solver."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from .models.container import Container
from .product_service import ResolvedProduct, to_solver_items
from .solver.optimizer import optimize_container
from app.db.container_loading_models import ContainerLoadingRun
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

SOLVER_OPTIONS = {
    "beam_width": 32,
    "solution_limit": 4,
    "max_blocks_per_sku": 140,
    "fixed_max_blocks_per_sku": 6,
    "stage_portfolio_limit": 6,
    "max_block_placements": 72,
    "min_support_ratio": 0.8,
    # The optimizer is a deterministic combinatorial search.  Give the full
    # SKU-order portfolio enough time to finish; the job API is asynchronous.
    "time_limit_seconds": 900,
    "lns_rounds": 12,
    "completion_candidate_limit": 24,
    "completion_max_additions": 500,
}


@dataclass
class _Job:
    job_id: str
    owner_open_id: str
    container: Container
    resolved: list[ResolvedProduct]
    status: str = "queued"
    progress: int = 0
    message: str = "等待计算"
    error: str = ""
    results: dict | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ContainerLoadingJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="container-loading")

    def create(self, owner_open_id: str, container: Container, resolved: list[ResolvedProduct]) -> _Job:
        job = _Job(
            job_id=str(uuid.uuid4()),
            owner_open_id=owner_open_id,
            container=container,
            resolved=resolved,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._persist(job, {
            "status": "queued",
            "container_payload": container.model_dump(mode="json"),
            "items_payload": [
                {
                    "product_market_parameter_id": str(item.product.id),
                    "solver_sku": item.solver_sku,
                    "sku": item.product.sku,
                    "msku": item.product.amazon_sku,
                    "product_name": item.product.product_name or item.product.name_zh or item.product.name_en,
                    "country": item.product.country_code,
                    "store": item.product.store,
                    "carton_length_cm": float(item.product.carton_length_cm),
                    "carton_width_cm": float(item.product.carton_width_cm),
                    "carton_height_cm": float(item.product.carton_height_cm),
                    "carton_weight_kg": float(item.product.carton_weight_kg),
                    "min_quantity": item.min_quantity,
                    "max_quantity": item.max_quantity,
                    "quantity_step": item.quantity_step,
                    "loading_stage": item.loading_stage,
                }
                for item in resolved
            ],
        }, create=True)
        self._executor.submit(self._run, job)
        return job

    def _persist(self, job: _Job, changes: dict, *, create: bool = False) -> None:
        """Write a durable audit snapshot without breaking the in-memory job API."""
        try:
            with SessionLocal() as session:
                row = session.get(ContainerLoadingRun, uuid.UUID(job.job_id))
                if row is None and create:
                    row = ContainerLoadingRun(
                        id=uuid.UUID(job.job_id),
                        owner_open_id=job.owner_open_id,
                        container_payload=changes.pop("container_payload"),
                        items_payload=changes.pop("items_payload"),
                    )
                    session.add(row)
                if row is None:
                    return
                for key, value in changes.items():
                    setattr(row, key, value)
                session.commit()
        except Exception:  # Persistence must not turn a valid calculation into a failed job.
            logger.exception("Failed to persist container-loading run %s", job.job_id)

    def get(self, job_id: str, owner_open_id: str) -> _Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.owner_open_id != owner_open_id:
                return None
            return job

    def audit(self, job_id: str, owner_open_id: str) -> dict | None:
        """Read a persisted calculation after an in-memory worker is gone."""
        try:
            with SessionLocal() as session:
                row = session.get(ContainerLoadingRun, uuid.UUID(job_id))
                if row is None or row.owner_open_id != owner_open_id:
                    return None
                return {
                    "job_id": str(row.id),
                    "owner_open_id": row.owner_open_id,
                    "status": row.status,
                    "container": row.container_payload,
                    "items": row.items_payload,
                    "results": row.results_payload,
                    "error": row.error_message or "",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
        except Exception:
            logger.exception("Failed to read persisted container-loading run %s", job_id)
            return None

    def _update(self, job: _Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
        persisted = {key: value for key, value in changes.items() if key in {"status", "error"}}
        if "error" in persisted:
            persisted["error_message"] = persisted.pop("error")
        if persisted:
            if persisted.get("status") == "running":
                persisted["started_at"] = datetime.now(timezone.utc)
            if persisted.get("status") in {"complete", "failed"}:
                persisted["finished_at"] = datetime.now(timezone.utc)
            self._persist(job, persisted)

    def _run(self, job: _Job) -> None:
        try:
            self._update(job, status="running", progress=5, message="正在准备商品参数")
            items = to_solver_items(job.resolved)
            results: dict[str, dict] = {}

            self._update(job, progress=10, message="正在计算统一阶段装柜方案")
            unified = optimize_container(
                job.container,
                items,
                "UNIFIED_STAGE_MAX",
                dict(SOLVER_OPTIONS),
            )
            results["UNIFIED_STAGE_MAX"] = unified.model_dump(mode="json")

            self._persist(job, {"results_payload": results})

            self._update(job, status="complete", progress=100, message="装柜方案计算完成", results=results)
        except Exception as exc:  # Keep the job API stable and expose a safe error to the UI.
            self._update(job, status="failed", progress=100, message="装柜方案计算失败", error=str(exc))


container_loading_jobs = ContainerLoadingJobManager()
