#!/usr/bin/env python3
"""Generate Data Hub API keys for subscription management.

Usage:
    python agent/scripts/gen_api_keys.py --email user@example.com --tier pro --days 30
    python agent/scripts/gen_api_keys.py --email user@example.com --tier basic
    python agent/scripts/gen_api_keys.py --list
    python agent/scripts/gen_api_keys.py --revoke <subscription_id>
    python agent/scripts/gen_api_keys.py --stats

Creates a subscription in ~/.vibe-trading/subscriptions.db and prints the
plaintext API key. The key is shown ONLY ONCE — store it securely.
"""

import argparse
import sys
from pathlib import Path

# Add parent (agent/) to path so we can import from src.
_AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_AGENT_DIR))


def cmd_create(args: argparse.Namespace) -> None:
    from src.data.subscription_store import get_subscription_store

    store = get_subscription_store()
    sub = store.create(
        email=args.email,
        tier=args.tier,
        quota_daily=args.quota,
        days=args.days,
    )
    print(f"Subscription created:")
    print(f"  ID:         {sub['id']}")
    print(f"  Email:      {sub['email']}")
    print(f"  Tier:       {sub['tier']}")
    print(f"  Quota/day:  {sub['quota_daily']}")
    print(f"  Expires:    {sub['expires_at'] or 'never'}")
    print(f"  API Key:    {sub['api_key']}")
    print()
    print("⚠️  Save the API key now — it will NOT be shown again.")
    print(f"   Use it as:  curl -H 'X-API-Key: {sub['api_key']}' https://your-server:8900/api/v1/market/overview")


def cmd_list(_args: argparse.Namespace) -> None:
    from src.data.subscription_store import get_subscription_store

    store = get_subscription_store()
    subs = store.list_all()
    if not subs:
        print("No subscriptions found.")
        return
    print(f"{'ID':<34} {'Email':<28} {'Tier':<8} {'Active':<8} {'Expires'}")
    print("-" * 110)
    for s in subs:
        active = "✓" if s["active"] else "✗"
        exp = s["expires_at"][:10] if s["expires_at"] else "never"
        print(f"{s['id']:<34} {s['email']:<28} {s['tier']:<8} {active:<8} {exp}")


def cmd_revoke(args: argparse.Namespace) -> None:
    from src.data.subscription_store import get_subscription_store

    store = get_subscription_store()
    ok = store.revoke(args.subscription_id)
    if ok:
        print(f"Subscription {args.subscription_id} revoked.")
    else:
        print(f"Subscription {args.subscription_id} not found.")
        sys.exit(1)


def cmd_stats(_args: argparse.Namespace) -> None:
    from src.data.subscription_store import get_subscription_store

    store = get_subscription_store()
    subs = store.list_all()
    active = sum(1 for s in subs if s["active"])
    by_tier: dict[str, int] = {}
    for s in subs:
        if s["active"]:
            tier = s["tier"]
            by_tier[tier] = by_tier.get(tier, 0) + 1
    print(f"Total subscriptions: {len(subs)}")
    print(f"Active:              {active}")
    print("By tier:", by_tier)


def main() -> None:
    parser = argparse.ArgumentParser(description="SigmX Data Hub — API key management")
    sub = parser.add_subparsers(dest="command")

    # create
    p = sub.add_parser("create", help="Create a subscription")
    p.add_argument("--email", required=True)
    p.add_argument("--tier", default="free", choices=["free", "basic", "pro"])
    p.add_argument("--quota", type=int, default=None, help="Daily request quota (default: tier default)")
    p.add_argument("--days", type=int, default=365, help="Validity in days (0=never)")
    p.set_defaults(func=cmd_create)

    # list
    p = sub.add_parser("list", help="List all subscriptions")
    p.set_defaults(func=cmd_list)

    # revoke
    p = sub.add_parser("revoke", help="Revoke a subscription")
    p.add_argument("subscription_id")
    p.set_defaults(func=cmd_revoke)

    # stats
    p = sub.add_parser("stats", help="Show Data Hub stats")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
