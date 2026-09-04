"""Read-only API for Agent-friendly LingXing analysis views."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.lingxing_analysis_queries import query_inventory, query_profit, query_sales, summarize
from app.services.lingxing_data_quality import build_lingxing_quality_report

router = APIRouter(prefix="/api/lingxing/analysis", tags=["lingxing-analysis"])


@router.get("/sales")
def sales(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    msku: str | None = None,
    asin: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return query_sales(db, start_date, end_date, msku, asin, limit, offset)


@router.get("/profit")
def profit(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    msku: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return query_profit(db, start_date, end_date, msku, limit, offset)


@router.get("/inventory")
def inventory(
    msku: str | None = None,
    asin: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return query_inventory(db, msku, asin, limit, offset)


@router.get("/summary")
def summary(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    msku: str | None = None,
    db: Session = Depends(get_db),
):
    return summarize(db, start_date, end_date, msku)


@router.get("/quality")
def quality(db: Session = Depends(get_db)):
    return build_lingxing_quality_report(db)
