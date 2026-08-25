"""Persistent daily sales cache for the logistics workflow."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class DailySalesRecord:
    sales_date: str
    sku: str
    amazon_sku: str
    product_name: str
    category: str
    store: str
    country: str
    platform: str
    volume: int
    trace_id: str = ""


class SalesCache:
    """SQLite-backed cache with explicit coverage states."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_sales (
                    sales_date TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    amazon_sku TEXT NOT NULL DEFAULT '',
                    product_name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    store TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT '',
                    volume INTEGER NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (sales_date, sku, amazon_sku, country, store)
                );
                CREATE INDEX IF NOT EXISTS idx_daily_sales_sku_date
                    ON daily_sales(sku, sales_date);
                CREATE TABLE IF NOT EXISTS sales_coverage (
                    sku TEXT NOT NULL,
                    sales_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (sku, sales_date)
                );
                CREATE TABLE IF NOT EXISTS mcp_raw_responses (
                    response_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def date_range(start: date, end: date) -> list[date]:
        days = (end - start).days
        return [start + timedelta(days=offset) for offset in range(days + 1)]

    def missing_dates(
        self,
        skus: Iterable[str],
        start: date,
        end: date,
    ) -> dict[str, list[date]]:
        sku_list = sorted(set(skus))
        wanted = self.date_range(start, end)
        if not sku_list:
            return {}
        with self._lock, self._connect() as connection:
            placeholders = ",".join("?" for _ in sku_list)
            rows = connection.execute(
                f"""
                SELECT sku, sales_date
                FROM sales_coverage
                WHERE sku IN ({placeholders})
                  AND sales_date BETWEEN ? AND ?
                  AND status = 'complete'
                """,
                [*sku_list, start.isoformat(), end.isoformat()],
            ).fetchall()
        covered = {(row["sku"], row["sales_date"]) for row in rows}
        return {
            sku: missing
            for sku in sku_list
            if (missing := [
                day for day in wanted if (sku, day.isoformat()) not in covered
            ])
        }

    def save_response(
        self,
        request: dict[str, Any],
        response: Any,
        trace_id: str = "",
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mcp_raw_responses
                    (response_id, request_json, response_json, trace_id, fetched_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    json.dumps(request, ensure_ascii=False, sort_keys=True),
                    json.dumps(response, ensure_ascii=False),
                    trace_id,
                    self._now(),
                ),
            )

    def save_daily_records(
        self,
        records: Iterable[DailySalesRecord],
        skus: Iterable[str],
        start: date,
        end: date,
        trace_id: str = "",
    ) -> None:
        fetched_at = self._now()
        record_list = list(records)
        requested_skus = sorted(set(skus))
        with self._lock, self._connect() as connection:
            for record in record_list:
                connection.execute(
                    """
                    INSERT INTO daily_sales
                        (sales_date, sku, amazon_sku, product_name, category,
                         store, country, platform, volume, trace_id, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sales_date, sku, amazon_sku, country, store)
                    DO UPDATE SET
                        product_name=excluded.product_name,
                        category=excluded.category,
                        platform=excluded.platform,
                        volume=excluded.volume,
                        trace_id=excluded.trace_id,
                        fetched_at=excluded.fetched_at
                    """,
                    (
                        record.sales_date,
                        record.sku,
                        record.amazon_sku,
                        record.product_name,
                        record.category,
                        record.store,
                        record.country,
                        record.platform,
                        record.volume,
                        record.trace_id or trace_id,
                        fetched_at,
                    ),
                )
            for sku in requested_skus:
                for day in self.date_range(start, end):
                    connection.execute(
                        """
                        INSERT INTO sales_coverage
                            (sku, sales_date, status, trace_id, fetched_at)
                        VALUES (?, ?, 'complete', ?, ?)
                        ON CONFLICT(sku, sales_date)
                        DO UPDATE SET
                            status='complete',
                            trace_id=excluded.trace_id,
                            fetched_at=excluded.fetched_at
                        """,
                        (sku, day.isoformat(), trace_id, fetched_at),
                    )

    def daily_records(
        self,
        sku: str,
        start: date,
        end: date,
    ) -> list[DailySalesRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sales_date, sku, amazon_sku, product_name, category,
                       store, country, platform, volume, trace_id
                FROM daily_sales
                WHERE sku = ? AND sales_date BETWEEN ? AND ?
                ORDER BY sales_date, country, store, amazon_sku
                """,
                (sku, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [DailySalesRecord(**dict(row)) for row in rows]

    def coverage_complete(self, sku: str, start: date, end: date) -> bool:
        with self._lock, self._connect() as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM sales_coverage
                WHERE sku = ? AND sales_date BETWEEN ? AND ?
                  AND status = 'complete'
                """,
                (sku, start.isoformat(), end.isoformat()),
            ).fetchone()[0]
        return count == len(self.date_range(start, end))

    def create_job(self, message: str = "排队中") -> str:
        job_id = uuid.uuid4().hex
        now = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_jobs(job_id, status, progress, message, created_at, updated_at)
                VALUES (?, 'queued', 0, ?, ?, ?)
                """,
                (job_id, message, now, now),
            )
        return job_id

    def update_job(
        self,
        job_id: str,
        status: str,
        progress: int,
        message: str = "",
        error: str = "",
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE sync_jobs
                SET status=?, progress=?, message=?, error=?, updated_at=?
                WHERE job_id=?
                """,
                (status, max(0, min(100, progress)), message, error, self._now(), job_id),
            )

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sync_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None
