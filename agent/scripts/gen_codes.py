"""Generate redeem codes and write them into credits.db + export a CSV.

Usage:
    python agent/scripts/gen_codes.py --credits 100 --count 50
    python agent/scripts/gen_codes.py --credits 50 --count 20 --prefix SIGMX --days 90

Codes are formatted ``{PREFIX}-XXXX-XXXX`` (uppercase alnum). They are written
to the ``redeem_codes`` table (status=unused) and also exported to
``~/credits_codes_<timestamp>.csv`` for distribution.
"""

from __future__ import annotations

import argparse
import csv
import random
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the agent package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.credits.store import CreditStore  # noqa: E402


def _gen_code(prefix: str, length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    chunk = "".join(random.choices(alphabet, k=length // 2))
    chunk2 = "".join(random.choices(alphabet, k=length // 2))
    return f"{prefix}-{chunk}-{chunk2}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate redeem codes.")
    parser.add_argument("--credits", type=int, required=True, help="积分面额（每码）")
    parser.add_argument("--count", type=int, default=10, help="生成数量")
    parser.add_argument("--prefix", default="SIGMX", help="兑换码前缀")
    parser.add_argument("--days", type=int, default=90, help="有效天数（0=永久）")
    args = parser.parse_args()

    store = CreditStore()
    expires_at = None
    if args.days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=args.days)).isoformat()

    codes: list[dict] = []
    seen: set[str] = set()
    attempts = 0
    while len(codes) < args.count and attempts < args.count * 5:
        attempts += 1
        code = _gen_code(args.prefix)
        if code in seen:
            continue
        seen.add(code)
        try:
            store.create_redeem_code(code, args.credits, expires_at)
            codes.append({"code": code, "credits": args.credits, "expires_at": expires_at or "永久"})
        except Exception as exc:
            print(f"skip duplicate/failed: {code} ({exc})")

    if not codes:
        print("未生成任何兑换码")
        return 1

    # Export CSV to home dir.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path.home() / f"credits_codes_{ts}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "credits", "expires_at"])
        w.writeheader()
        w.writerows(codes)

    print(f"已生成 {len(codes)} 个兑换码，每个 {args.credits} 积分")
    print(f"有效期：{expires_at or '永久'}")
    print(f"CSV 已导出：{out}")
    for c in codes[:10]:
        print(f"  {c['code']}  ({c['credits']} 积分)")
    if len(codes) > 10:
        print(f"  ... 共 {len(codes)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
