"""Tests for B-batch additions: fq_factors + minute_bars store/sync, and the
new /api/v1 endpoints (fq-factors, minute with aggregation, wolf passthrough)."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import sigmx_routes
from src.api.sigmx_routes import register_sigmx_routes
from src.data.market_store import MarketStore

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "market.db"
    store = MarketStore(str(db))
    _seed(store)
    monkeypatch.setattr(sigmx_routes, "DB_PATH", str(db))
    app = FastAPI()
    register_sigmx_routes(app)
    yield store, TestClient(app)
    store._conn.close()


def _seed(store: MarketStore) -> None:
    store.upsert_fq_factors("2026-08-14", [
        {"code": "000001.SZ", "adj_factor": 105.3},
        {"code": "600519.SH", "adj_factor": 88.1},
    ])
    # 4 bars of 5m for one code: 09:35, 09:40, 09:45, 09:50
    bars = [
        {"bar_time": f"09:{m}", "open": 10.0 + i * 0.1, "high": 10.1 + i * 0.1,
         "low": 9.9 + i * 0.1, "close": 10.05 + i * 0.1, "volume": 1000 + i * 100,
         "total_amt": 1.0e6 + i * 1e5}
        for i, m in enumerate(["35", "40", "45", "50"])
    ]
    store.upsert_minute_bars("000001", "2026-08-14", bars)


class TestFqFactorsStore:
    def test_upsert_and_prune(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        store.upsert_fq_factors("2026-08-13", [{"code": "000001.SZ", "adj_factor": 105.0}])
        store.upsert_fq_factors("2026-08-14", [
            {"code": "000001.SZ", "adj_factor": 105.3},
            {"code": "000001.SZ", "adj_factor": 105.9},  # dup PK within batch
        ])
        n = store._conn.execute("SELECT COUNT(*) FROM fq_factors").fetchone()[0]
        # PK is (code, trade_date): two dates = 2 rows; dup in-batch replaced.
        assert n == 2
        factor = store._conn.execute(
            "SELECT adj_factor FROM fq_factors WHERE trade_date='2026-08-14'").fetchone()[0]
        assert factor == 105.9
        store._conn.close()


class TestMinuteBarsStore:
    def test_upsert_idempotent(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        rows = [{"bar_time": "09:35", "open": 10, "high": 10, "low": 10,
                 "close": 10, "volume": 1, "total_amt": 1}]
        assert store.upsert_minute_bars("000001", "2026-08-14", rows) == 1
        assert store.upsert_minute_bars("000001", "2026-08-14", rows) == 1
        n = store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
        assert n == 1

    def test_prune_keeps_recent(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        for d in ("2026-08-12", "2026-08-13", "2026-08-14"):
            store.upsert_minute_bars("000001", d, [
                {"bar_time": "09:35", "close": 10, "volume": 1, "total_amt": 1}])
        store.prune_minute_bars(2)
        dates = [r[0] for r in store._conn.execute(
            "SELECT DISTINCT trade_date FROM minute_bars ORDER BY trade_date").fetchall()]
        assert dates == ["2026-08-13", "2026-08-14"]
        store._conn.close()


class TestSyncMinuteBarsFor:
    def test_writes_bars_from_tpdog(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        fake = [{"date": "2026-08-14 09:35:00", "open": 10.0, "high": 10.2,
                 "low": 9.9, "close": 10.1, "volume": 5000, "total_amt": 5.1e5}]
        with mock.patch("src.data.tpdog_client.call", return_value=fake) as mc:
            total = market_sync.sync_minute_bars_for(store, "2026-08-14", ["000001"])
        assert total == 1
        assert mc.call_args.kwargs["code"] == "sz.000001"
        row = store._conn.execute(
            "SELECT bar_time, close FROM minute_bars").fetchone()
        assert row[0] == "09:35"
        assert row[1] == 10.1
        store._conn.close()

    def test_single_code_failure_skipped(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        with mock.patch("src.data.tpdog_client.call",
                        side_effect=RuntimeError("boom")):
            total = market_sync.sync_minute_bars_for(store, "2026-08-14", ["000001"])
        assert total == 0
        store._conn.close()


class TestFqFactorsEndpoint:
    def test_history(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/fq-factors", params={"code": "000001.SZ"})
        body = r.json()
        assert body["data"]["items"][0]["adj_factor"] == 105.3

    def test_unknown_404(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/fq-factors", params={"code": "999999"})
        assert r.status_code == 404


class TestMinuteEndpoint:
    def test_5m_bars(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/minute", params={"code": "000001"})
        body = r.json()
        items = body["data"]["items"]
        assert len(items) == 4
        assert items[0]["bar_time"] == "09:35"

    def test_15m_aggregates_three_bars(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/minute", params={"code": "000001", "period": "15m"})
        items = r.json()["data"]["items"]
        assert len(items) == 2  # bars 1-3 bucket, bar 4 own bucket
        first = items[0]
        assert first["high"] == pytest.approx(10.3)  # max of first three highs
        assert first["volume"] == pytest.approx(1000 + 1100 + 1200)  # summed

    def test_bad_period_400(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/minute", params={"code": "000001", "period": "7m"})
        assert r.status_code == 400


class TestWolfPassthrough:
    def test_ticks_passthrough(self, client, monkeypatch):
        _, c = client
        fake_rows = [{"t": "09:31:00", "cjj": 10.5, "bs": 1}] * 3
        with mock.patch("src.data.wolf_client.call", return_value=fake_rows):
            r = c.get("/api/v1/stocks/ticks", params={"code": "000001"})
        body = r.json()
        assert body["ok"] is True
        assert body["meta"]["passthrough"] == "wolf"
        assert body["data"]["count"] == 3

    def test_unconfigured_502(self, client):
        _, c = client
        from src.data.wolf_client import WolfNotConfiguredError
        with mock.patch("src.data.wolf_client.call", side_effect=WolfNotConfiguredError()):
            r = c.get("/api/v1/stocks/quote5", params={"code": "000001"})
        assert r.status_code == 502
        assert r.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
