"""PostgreSQL-backed cache for logistics sales and sync jobs."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import text

from app.db.session import SessionLocal
from app.workflows.sales_cache import DailySalesRecord


class PostgresSalesCache:
    def __init__(self):
        self._lock = threading.RLock()

    @staticmethod
    def _now():
        return datetime.now().astimezone()

    @staticmethod
    def date_range(start: date, end: date) -> list[date]:
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]

    def missing_dates(self, mskus: Iterable[str], start: date, end: date):
        msku_list = sorted(set(mskus))
        if not msku_list:
            return {}
        with SessionLocal() as s:
            rows = s.execute(text("SELECT sku, sales_date FROM sales_coverage WHERE sku = ANY(:mskus) AND sales_date BETWEEN :start AND :end AND status='complete'"), {"mskus": msku_list, "start": start, "end": end}).all()
        covered = {(r.sku, r.sales_date) for r in rows}
        return {msku: [d for d in self.date_range(start, end) if (msku, d) not in covered] for msku in msku_list if any((msku, d) not in covered for d in self.date_range(start, end))}

    def save_response(self, request: dict[str, Any], response: Any, trace_id: str = ""):
        with SessionLocal.begin() as s:
            s.execute(text("INSERT INTO mcp_raw_responses(response_id, request_json, response_json, trace_id, fetched_at) VALUES (:id,:request,:response,:trace,:fetched) ON CONFLICT(response_id) DO NOTHING"), {"id": uuid.uuid4().hex, "request": json.dumps(request, ensure_ascii=False, sort_keys=True), "response": json.dumps(response, ensure_ascii=False), "trace": trace_id, "fetched": self._now()})

    def save_daily_records(self, records: Iterable[DailySalesRecord], mskus: Iterable[str], start: date, end: date, trace_id: str = "", replace_existing: bool = False):
        record_list = list(records)
        requested = sorted(set(mskus))
        with SessionLocal.begin() as s:
            if replace_existing and requested:
                s.execute(text("DELETE FROM daily_sales WHERE amazon_sku = ANY(:mskus) AND sales_date BETWEEN :start AND :end"), {"mskus": requested, "start": start, "end": end})
            for r in record_list:
                s.execute(text("""INSERT INTO daily_sales(sales_date,sku,amazon_sku,product_name,category,store,country,platform,volume,trace_id,fetched_at) VALUES (:d,:sku,:msku,:name,:category,:store,:country,:platform,:volume,:trace,:fetched) ON CONFLICT(sales_date,sku,amazon_sku,country,store) DO UPDATE SET product_name=EXCLUDED.product_name, category=EXCLUDED.category, platform=EXCLUDED.platform, volume=EXCLUDED.volume, trace_id=EXCLUDED.trace_id, fetched_at=EXCLUDED.fetched_at"""), {"d": date.fromisoformat(r.sales_date), "sku": r.sku, "msku": r.amazon_sku, "name": r.product_name, "category": r.category, "store": r.store, "country": r.country, "platform": r.platform, "volume": r.volume, "trace": r.trace_id or trace_id, "fetched": self._now()})
            for msku in requested:
                for d in self.date_range(start, end):
                    s.execute(text("INSERT INTO sales_coverage(sku,sales_date,status,trace_id,fetched_at) VALUES (:msku,:d,'complete',:trace,:fetched) ON CONFLICT(sku,sales_date) DO UPDATE SET status='complete', trace_id=EXCLUDED.trace_id, fetched_at=EXCLUDED.fetched_at"), {"msku": msku, "d": d, "trace": trace_id, "fetched": self._now()})

    def daily_records(self, msku: str, start: date, end: date):
        with SessionLocal() as s:
            rows = s.execute(text("SELECT sales_date,sku,amazon_sku,product_name,category,store,country,platform,volume,trace_id FROM daily_sales WHERE amazon_sku=:msku AND sales_date BETWEEN :start AND :end ORDER BY sales_date,country,store,amazon_sku"), {"msku": msku, "start": start, "end": end}).mappings().all()
        return [DailySalesRecord(sales_date=r["sales_date"].isoformat(), sku=r["sku"], amazon_sku=r["amazon_sku"], product_name=r["product_name"], category=r["category"], store=r["store"], country=r["country"], platform=r["platform"], volume=r["volume"], trace_id=r["trace_id"]) for r in rows]

    def coverage_complete(self, msku: str, start: date, end: date) -> bool:
        with SessionLocal() as s:
            n = s.execute(text("SELECT COUNT(*) FROM sales_coverage WHERE sku=:msku AND sales_date BETWEEN :start AND :end AND status='complete'"), {"msku": msku, "start": start, "end": end}).scalar_one()
        return n == len(self.date_range(start, end))

    def create_job(self, message: str = "排队中") -> str:
        job_id = uuid.uuid4().hex; now = self._now()
        with SessionLocal.begin() as s:
            s.execute(text("INSERT INTO sync_jobs(job_id,status,progress,message,created_at,updated_at) VALUES (:id,'queued',0,:message,:now,:now)"), {"id": job_id, "message": message, "now": now})
        return job_id

    def update_job(self, job_id: str, status: str, progress: int, message: str = "", error: str = ""):
        with SessionLocal.begin() as s:
            s.execute(text("UPDATE sync_jobs SET status=:status,progress=:progress,message=:message,error=:error,updated_at=:now WHERE job_id=:id"), {"id": job_id, "status": status, "progress": max(0, min(100, progress)), "message": message, "error": error, "now": self._now()})

    def job(self, job_id: str):
        with SessionLocal() as s:
            row = s.execute(text("SELECT * FROM sync_jobs WHERE job_id=:id"), {"id": job_id}).mappings().first()
        return dict(row) if row else None
