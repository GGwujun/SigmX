"""Tests for the /api/v1/* data endpoints in sigmx_routes.

Pattern: build a temp market.db via MarketStore, point sigmx_routes.DB_PATH at
it, and hit endpoints through TestClient with auth disabled (non-Data-Hub mode
passes through automatically).
"""
import sys
from pathlib import Path

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
    store._conn.close()
    monkeypatch.setattr(sigmx_routes, "DB_PATH", str(db))
    app = FastAPI()
    register_sigmx_routes(app)
    return TestClient(app)


def _seed(store: MarketStore) -> None:
    store.upsert_daily_bars(
        "000001",
        [
            {"code": "000001", "trade_date": "2026-08-13", "open": 10.0, "high": 10.5,
             "low": 9.8, "close": 10.2, "volume": 1000000, "total_amt": 10200000,
             "rise_rate": 1.2, "name": "平安银行"},
            {"code": "000001", "trade_date": "2026-08-14", "open": 10.2, "high": 10.8,
             "low": 10.1, "close": 10.6, "volume": 1200000, "total_amt": 12700000,
             "rise_rate": 3.9, "name": "平安银行"},
        ],
        source="test", sync_run_id="",
    )
    with store._write_transaction():
        store._conn.executemany(
            "INSERT OR REPLACE INTO stock_daily_basic "
            "(code, trade_date, close, pe, pb, total_mv, circ_mv, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            [("000001", "2026-08-14", 10.6, 5.1, 0.5, 2.1e6, 2.0e6)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO etf_daily "
            "(code, trade_date, open, high, low, close, volume, total_amt, rise, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("510050", "2026-08-14", 3.0, 3.1, 2.9, 3.05, 500000, 1520000, 1.0)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO fund_daily "
            "(code, trade_date, open, high, low, close, volume, total_amt, nav, iopv, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("501018", "2026-08-14", 1.5, 1.6, 1.4, 1.55, 80000, 124000, 1.52, 1.53)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO board_daily "
            "(board_code, trade_date, name, board_type, close, rise_rate, turnover_rate, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            [("BK0001", "2026-08-14", "银行", "industry", 1050.0, 2.3, 1.1)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO board_members "
            "(board_code, board_type, stock_code, stock_name, updated_at) "
            "VALUES (?,?,?,?,datetime('now'))",
            [("BK0001", "industry", "000001", "平安银行")],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO realtime_quote_snapshot "
            "(trade_date, code, name, snapshot_at, price, pre_close, rise_rate, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            [("2026-08-14", "000001", "平安银行", "2026-08-14T14:55:00", 10.6, 10.2, 3.9)],
        )


class TestStocksDaily:
    def test_returns_bars_desc(self, client):
        r = client.get("/api/v1/stocks/daily", params={"code": "000001"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["data"]["count"] == 2
        assert body["data"]["items"][0]["trade_date"] == "2026-08-14"

    def test_date_range_filter(self, client):
        r = client.get("/api/v1/stocks/daily",
                       params={"code": "000001", "end": "2026-08-13"})
        assert r.json()["data"]["count"] == 1

    def test_unknown_code_404(self, client):
        r = client.get("/api/v1/stocks/daily", params={"code": "999999"})
        assert r.status_code == 404
        assert r.json()["ok"] is False

    def test_missing_code_422(self, client):
        r = client.get("/api/v1/stocks/daily")
        assert r.status_code == 422


class TestStocksDailyBasic:
    def test_latest_date_items(self, client):
        r = client.get("/api/v1/stocks/daily-basic")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["trade_date"] == "2026-08-14"
        item = body["data"]["items"][0]
        assert item["code"] == "000001"
        assert item["pe"] == 5.1

    def test_codes_filter(self, client):
        r = client.get("/api/v1/stocks/daily-basic", params={"codes": "300999"})
        assert r.json()["data"]["count"] == 0


class TestEtfFundDaily:
    def test_etf_daily(self, client):
        r = client.get("/api/v1/etf/daily", params={"code": "510050"})
        body = r.json()
        assert body["ok"] is True
        assert body["data"]["items"][0]["close"] == 3.05
        assert "nav" not in body["data"]["items"][0]

    def test_fund_daily_has_nav_iopv(self, client):
        r = client.get("/api/v1/fund/daily", params={"code": "501018"})
        item = r.json()["data"]["items"][0]
        assert item["nav"] == 1.52
        assert item["iopv"] == 1.53

    def test_etf_unknown_404(self, client):
        r = client.get("/api/v1/etf/daily", params={"code": "999999"})
        assert r.status_code == 404


class TestBoards:
    def test_boards_daily_by_code(self, client):
        r = client.get("/api/v1/boards/daily", params={"board_code": "BK0001"})
        body = r.json()
        assert body["data"]["items"][0]["rise_rate"] == 2.3

    def test_boards_daily_by_date(self, client):
        r = client.get("/api/v1/boards/daily")
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 1

    def test_board_members(self, client):
        r = client.get("/api/v1/boards/members", params={"board_code": "BK0001"})
        body = r.json()
        assert body["data"]["items"][0]["stock_code"] == "000001"

    def test_board_members_unknown_404(self, client):
        r = client.get("/api/v1/boards/members", params={"board_code": "BK9999"})
        assert r.status_code == 404


class TestQuotesRealtime:
    def test_realtime(self, client):
        r = client.get("/api/v1/quotes/realtime", params={"codes": "000001"})
        body = r.json()
        assert body["data"]["items"][0]["price"] == 10.6

    def test_empty_codes_400(self, client):
        r = client.get("/api/v1/quotes/realtime", params={"codes": ","})
        assert r.status_code == 400


class TestHealthEndpointList:
    def test_health_lists_new_endpoints(self, client):
        r = client.get("/api/v1/health")
        eps = r.json()["endpoints"]
        assert "/api/v1/stocks/daily" in eps
        assert "/api/v1/quotes/realtime" in eps
