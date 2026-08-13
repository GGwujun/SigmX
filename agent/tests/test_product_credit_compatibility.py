"""Compatibility between the new product CreditLedger and the legacy CreditStore.

Task 2 plan Step 4/5: legacy ``credits.db`` balances migrate into permanent
product lots, the legacy store is preserved for rollback, and the existing
``CreditStore.consume/refund`` signatures used by AlphaForge / fund-arbitrage /
credits routes keep working unchanged.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from src.credits.store import CreditStore
from src.product.credits import CreditLedger, migrate_legacy_balances
from src.product.store import ProductStore


def test_legacy_credit_store_signatures_unchanged() -> None:
    """The four route callers must keep compiling against the old surface."""
    sig = {name: inspect.signature(getattr(CreditStore, name))
           for name in ("consume", "refund", "get_balance", "add_credits")}
    # consume(user_id, amount, ref, note) — alpha_forge_routes / fund_routes.
    assert list(sig["consume"].parameters) == ["self", "user_id", "amount", "ref", "note"]
    # refund(user_id, amount, ref, note) — failure path in both metered routes.
    assert list(sig["refund"].parameters) == ["self", "user_id", "amount", "ref", "note"]
    assert list(sig["get_balance"].parameters) == ["self", "user_id"]
    assert list(sig["add_credits"].parameters) == ["self", "user_id", "delta", "tx_type", "ref", "note"]


def test_legacy_store_still_functions_alongside_new_ledger(tmp_path: Path) -> None:
    """Old store keeps working during the migration window — both DBs coexist."""
    legacy = CreditStore(tmp_path / "credits.db")
    assert legacy.consume("u1", 5, "run-x", "probe") is False  # no balance → False
    legacy.add_credits("u1", 100, "admin", "seed", "test")
    assert legacy.consume("u1", 5, "run-x", "probe") is True
    assert legacy.get_balance("u1") == 95


def test_migrate_legacy_balances_into_permanent_lots(tmp_path: Path) -> None:
    """Each legacy balance becomes one non-expiring product lot; credits.db untouched."""
    legacy = CreditStore(tmp_path / "credits.db")
    legacy.add_credits("alice", 100, "admin", "seed", "t")
    legacy.add_credits("bob", 7, "redeem", "CODE1", "t")

    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)

    migrated = migrate_legacy_balances(ledger, legacy)
    assert migrated == {"alice": 100, "bob": 7}

    assert ledger.balance("alice").available == 100
    assert ledger.balance("bob").available == 7
    # Migrated lots are permanent.
    alice_lots = ledger.list_lots("alice")
    assert len(alice_lots) == 1
    assert alice_lots[0]["expires_at"] is None
    assert alice_lots[0]["source"] == "legacy_migration"


def test_migration_is_idempotent_and_does_not_touch_legacy_db(tmp_path: Path) -> None:
    """Re-running migration is a no-op; legacy DB rows are unchanged."""
    legacy = CreditStore(tmp_path / "credits.db")
    legacy.add_credits("alice", 100, "admin", "seed", "t")

    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)

    migrate_legacy_balances(ledger, legacy)
    second = migrate_legacy_balances(ledger, legacy)
    assert second == {}  # nothing new — already migrated

    # Balance didn't double.
    assert ledger.balance("alice").available == 100

    # Legacy DB is intact (rollback path still valid).
    assert legacy.get_balance("alice") == 100


def test_alphaforge_failure_refunds_exactly_once(tmp_path: Path) -> None:
    """Mirrors alpha_forge_routes: reserve(50) → settle is skipped on failure → refund once."""
    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")

    res = ledger.reserve("u1", 50, operation="alphaforge", idempotency_key="run-9")
    assert ledger.balance("u1").available == 50  # pre-deducted

    # Task failed → refund. Calling refund twice (a retry storm) must not double-credit.
    ledger.refund(res.reservation_id, idempotency_key="run-9")
    ledger.refund(res.reservation_id, idempotency_key="run-9")
    assert ledger.balance("u1").available == 100
