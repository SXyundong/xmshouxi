"""In-process asynchronous jobs for the CPU-heavy container solver."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models.container import Container
from .product_service import ResolvedProduct, to_solver_items
from .solver.optimizer import optimize_container

SOLVER_OPTIONS = {
    "beam_width": 32,
    "solution_limit": 4,
    "max_blocks_per_sku": 140,
    "max_block_placements": 72,
    "min_support_ratio": 0.8,
    "time_limit_seconds": 300,
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
        self._executor.submit(self._run, job)
        return job

    def get(self, job_id: str, owner_open_id: str) -> _Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.owner_open_id != owner_open_id:
                return None
            return job

    def _update(self, job: _Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

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

            self._update(job, status="complete", progress=100, message="装柜方案计算完成", results=results)
        except Exception as exc:  # Keep the job API stable and expose a safe error to the UI.
            self._update(job, status="failed", progress=100, message="装柜方案计算失败", error=str(exc))


container_loading_jobs = ContainerLoadingJobManager()
