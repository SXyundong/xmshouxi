"""Print a read-only LingXing data quality report."""

from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.services.lingxing_data_quality import build_lingxing_quality_report


def main() -> int:
    session = SessionLocal()
    try:
        print(json.dumps(build_lingxing_quality_report(session), ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
