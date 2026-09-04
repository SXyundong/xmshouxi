"""Sync LingXing FBA inventory snapshots."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.workflows.lingxing_inventory_sync import LingXingInventorySync


async def _run(args: argparse.Namespace) -> int:
    result = await LingXingInventorySync().run(
        sids=args.sid or None,
        msku=args.msku,
        page_size=args.page_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步领星 FBA 库存快照")
    parser.add_argument("--sid", action="append", type=int, help="店铺 ID，可重复传入")
    parser.add_argument("--msku", help="限定 MSKU")
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001
        print(f"领星库存同步失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
