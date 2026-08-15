"""One-shot backfill of 5m minute bars for explicit codes/dates.

Not wired into the scheduled worker (per plan B2): run manually when you want
recent hot stocks' intraday trajectory backfilled, e.g.

    python scripts/backfill_minute_bars.py --date 2026-08-14 --codes 000001,600519
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.market_store import MarketStore
from src.data.market_sync import sync_minute_bars_for


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="trade date YYYY-MM-DD")
    parser.add_argument("--codes", required=True, help="comma-separated codes")
    parser.add_argument("--db", default=None, help="market.db path override")
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    if not codes:
        parser.error("--codes is empty")

    store = MarketStore(args.db) if args.db else MarketStore()
    total = sync_minute_bars_for(store, args.date, codes)
    print(f"backfilled {total} rows for {len(codes)} codes @ {args.date}")
    store._conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
