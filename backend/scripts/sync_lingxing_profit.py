"""Sync LingXing MSKU profit facts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date

from app.workflows.lingxing_profit_sync import LingXingProfitSync


async def _run(args: argparse.Namespace) -> int:
    result = await LingXingProfitSync().run(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        mskus=args.msku or None,
        currency_code=args.currency,
        page_size=args.page_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步领星 MSKU 利润事实")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--msku", action="append")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001
        print(f"领星利润同步失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
