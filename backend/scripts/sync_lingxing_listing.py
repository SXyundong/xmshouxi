"""Run one idempotent LingXing ``erp_listing`` sync.

Run from ``backend`` after applying Alembic migrations::

    python -m scripts.sync_lingxing_listing --page-size 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.workflows.lingxing_listing_sync import LingXingListingSync


async def _run(page_size: int) -> int:
    summary = await LingXingListingSync(page_size=page_size).run()
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步领星 erp_listing 到本地 PostgreSQL")
    parser.add_argument("--page-size", type=int, default=200, help="erp_listing 分页大小")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.page_size))
    except Exception as exc:  # noqa: BLE001 - CLI should provide a concise failure message.
        print(f"领星 Listing 同步失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
