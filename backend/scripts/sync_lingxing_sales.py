"""Sync daily sales from LingXing product performance."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date

from app.workflows.lingxing_sales_sync import LingXingSalesSync


async def _run(args: argparse.Namespace) -> int:
    result = await LingXingSalesSync().run(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        mskus=args.msku or None,
        currency_code=args.currency,
        page_size=args.page_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步领星产品表现日销量")
    parser.add_argument("--start-date", required=True, help="开始日期，YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="结束日期，YYYY-MM-DD")
    parser.add_argument("--msku", action="append", help="限定 MSKU，可重复传入")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--page-size", type=int, default=1000)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - concise CLI error
        print(f"领星销量同步失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
