"""Tests for C-batch: unusual_event / call_auction_snapshot / hot_money tables,
sync functions (wolf + degraded paths), scheduling windows, and 6 endpoints."""
import sys
from datetime import time as dtime
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
    store.upsert_unusual_events("2026-08-14", [
        {"code": "000001", "time": "09:35:12", "name": "平安银行", "type": 13,
         "type_name": "火箭发射", "price": 10.5, "volume": "12300", "rise_rate": 5.1},
        {"code": "000001", "time": "09:35:12", "name": "平安银行", "type": 11,
         "type_name": "大笔买入", "price": 10.5, "volume": "8000", "rise_rate": 5.1},
        {"code": "600519", "time": "10:01:33", "name": "贵州茅台", "type": 1,
         "type_name": "封涨停板", "price": 1800.0, "volume": "500", "rise_rate": 10.0},
    ])
    store.upsert_call_auction("2026-08-14", [
        {"code": "000001", "time": "09:20", "price": 10.4, "pre_close": 10.2,
         "change_pct": 1.96, "auction_volume": 12000, "auction_amount": 1.25e5,
         "unmatched_volume": 3000, "unmatched_amount": 3.1e4, "buy_sell_side": 1},
        {"code": "000001", "time": "09:25", "price": 10.5, "pre_close": 10.2,
         "change_pct": 2.94, "auction_volume": 25000, "auction_amount": 2.6e5,
         "unmatched_volume": 8000, "unmatched_amount": 8.4e4, "buy_sell_side": 1},
        {"code": "600519", "time": "09:25", "price": 1980.0, "pre_close": 1800.0,
         "change_pct": 10.0, "auction_volume": 300, "auction_amount": 5.9e5,
         "buy_sell_side": 1},
    ])
    store.upsert_hot_money_daily("2026-08-14", [
        {"code": "000001", "hot_code": "H001", "name": "平安银行", "hot_name": "赵老哥",
         "reason": "题材", "rise_rate": 10.0, "buy_amt": 8.0e7, "sell_amt": 0.0,
         "net": 8.0e7, "buy_ratio": 0.42, "sell_ratio": 0.0},
    ])
    store.upsert_hot_money_list([
        {"hot_code": "H001", "hot_name": "赵老哥", "description": "知名游资"},
    ])
    store._conn.executemany(
        "INSERT OR REPLACE INTO hot_list "
        "(trade_date, code, name, rank, hot_value, change_pct, source, updated_at) "
        "VALUES (?,?,?,?,?,?,?,datetime('now'))",
        [("2026-08-13", "000001", "平安银行", 3, 8.8e5, 2.0, "ths"),
         ("2026-08-14", "000001", "平安银行", 1, 9.9e5, 10.0, "ths")],
    )


# ---------------- store layer ----------------

class TestStoreUpserts:
    def test_unusual_pk_dedup_same_type(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        rows = [{"code": "000001", "time": "09:35:12", "type": 13, "volume": "1"}]
        store.upsert_unusual_events("2026-08-14", rows)
        store.upsert_unusual_events("2026-08-14", rows)  # same PK replaced
        n = store._conn.execute("SELECT COUNT(*) FROM unusual_event").fetchone()[0]
        assert n == 1
        store._conn.close()

    def test_call_auction_prune(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        for d in ("2026-08-12", "2026-08-13", "2026-08-14"):
            store.upsert_call_auction(d, [{"code": "000001", "time": "09:25", "price": 1}])
        store.prune_call_auction(2)
        dates = [r[0] for r in store._conn.execute(
            "SELECT DISTINCT trade_date FROM call_auction_snapshot ORDER BY trade_date").fetchall()]
        assert dates == ["2026-08-13", "2026-08-14"]
        store._conn.close()

    def test_hot_money_list_overwrites(self, tmp_path):
        store = MarketStore(str(tmp_path / "t.db"))
        store.upsert_hot_money_list([{"hot_code": "H001", "hot_name": "旧名"}])
        store.upsert_hot_money_list([{"hot_code": "H001", "hot_name": "新名"}])
        name = store._conn.execute(
            "SELECT hot_name FROM hot_money_list").fetchone()[0]
        assert name == "新名"
        store._conn.close()


# ---------------- sync layer ----------------

class TestSyncUnusual:
    def test_post_close_pulls_history(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        fake = [{"code": "000001", "name": "平安银行", "time": "2026-08-14 09:35:12",
                 "type": 13, "type_name": "火箭发射", "price": 10.5,
                 "volume": "12300", "rise_rate": 5.1}]
        with mock.patch("src.data.tpdog_client.call", return_value=fake), \
             mock.patch("src.data.trade_calendar.cn_market_phase", return_value="post_close"):
            total = market_sync._sync_unusual(store, "2026-08-14")
        assert total == 1
        row = store._conn.execute(
            "SELECT time, volume FROM unusual_event").fetchone()
        assert row[0] == "09:35:12"
        assert row[1] == 12300.0
        store._conn.close()

    def test_intraday_uses_realtime_endpoint(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        with mock.patch("src.data.tpdog_client.call", return_value=[]) as mc, \
             mock.patch("src.data.trade_calendar.cn_market_phase", return_value="in_session"):
            market_sync._sync_unusual(store, "2026-08-14")
        assert mc.call_args.args[0] == "unusual/get"
        store._conn.close()


class TestSyncCallAuction:
    def test_wolf_primary_path(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        fake = [{"code": "000001", "t": "2026-08-14 09:20:00", "p": 10.4, "pc": 10.2,
                 "zf": 1.96, "jv": 12000, "je": 1.25e5, "nv": 3000, "ne": 3.1e4, "bs": 1}]
        with mock.patch("src.data.wolf_client.is_configured", return_value=True), \
             mock.patch("src.data.wolf_client.call", return_value=fake), \
             mock.patch("src.data.market_sync._sync_call_auction"):
            # patch prune away via env-safe path: call inner logic directly
            pass
        # direct: replicate mapping assertions through real function
        with mock.patch("src.data.wolf_client.is_configured", return_value=True), \
             mock.patch("src.data.wolf_client.call", return_value=fake):
            total = market_sync._sync_call_auction(store, "2026-08-14")
        assert total >= 1
        row = store._conn.execute(
            """SELECT time, change_pct, unmatched_volume, source
               FROM call_auction_snapshot WHERE code='000001'""").fetchone()
        assert row[0] == "09:20"
        assert row[1] == 1.96
        assert row[2] == 3000
        assert row[3] == "wolf"
        store._conn.close()

    def test_degraded_tpdog_path_when_wolf_missing(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        # yesterday's pool provides the code universe
        store._conn.execute(
            "INSERT OR REPLACE INTO stock_pool (trade_date, code, pool_type, updated_at) "
            "VALUES ('2026-08-13', '000001.SZ', 'limitup', datetime('now'))")
        fake_auction = [{"code": "sz.000001", "time": "2026-08-14 09:20:00",
                         "price": 10.4, "rise_rate": 1.96, "volume": 12000, "buy_sell": 1}]
        with mock.patch("src.data.wolf_client.is_configured", return_value=False), \
             mock.patch("src.data.tpdog_client.call",
                        side_effect=lambda path, **kw: fake_auction if "call_auction" in path else []):
            market_sync._sync_call_auction(store, "2026-08-14")
        row = store._conn.execute(
            "SELECT source FROM call_auction_snapshot").fetchone()
        assert row[0] == "tpdog"
        store._conn.close()


class TestSyncHotMoney:
    def test_daily_and_roster(self, tmp_path):
        from src.data import market_sync
        store = MarketStore(str(tmp_path / "t.db"))
        daily = [{"code": "000001", "hot_code": "H001", "hot_name": "赵老哥",
                  "buy_amt": 1.0, "net": 0.8}]
        roster = [{"hot_code": "H001", "hot_name": "赵老哥", "desc": "知名游资"}]
        with mock.patch("src.data.tpdog_client.call", side_effect=[daily, roster]):
            n1 = market_sync._sync_hot_money(store, "2026-08-14")
            n2 = market_sync._sync_hot_money_list(store, "2026-08-14")
        assert n1 == 1 and n2 == 1
        store._conn.close()


# ---------------- endpoints ----------------

class TestUnusualEndpoints:
    def test_list_desc(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/unusual")
        items = r.json()["data"]["items"]
        assert len(items) == 3
        assert items[0]["time"] >= items[-1]["time"]

    def test_type_filter(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/unusual", params={"type": 1})
        assert r.json()["data"]["count"] == 1

    def test_types_dict(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/unusual/types")
        items = r.json()["data"]["items"]
        assert len(items) == 22
        assert items[0]["type_name"] == "封涨停板"


class TestCallAuctionEndpoint:
    def test_code_evolution(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/call-auction", params={"code": "000001"})
        items = r.json()["data"]["items"]
        assert len(items) == 2  # 09:20 + 09:25
        assert items[0]["time"] == "09:20"

    def test_latest_market_snapshot(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/call-auction", params={"latest": "1"})
        items = r.json()["data"]["items"]
        assert all(i["time"] == "09:25" for i in items)
        assert items[0]["code"] == "600519"  # biggest auction amount first

    def test_no_params_400(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/call-auction")
        assert r.status_code == 400


class TestHotMoneyEndpoints:
    def test_daily(self, client):
        _, c = client
        r = c.get("/api/v1/hot-money/daily")
        item = r.json()["data"]["items"][0]
        assert item["hot_name"] == "赵老哥"

    def test_hot_name_filter(self, client):
        _, c = client
        r = c.get("/api/v1/hot-money/daily", params={"hot_name": "不存在"})
        assert r.status_code == 404

    def test_roster(self, client):
        _, c = client
        r = c.get("/api/v1/hot-money/list")
        assert r.json()["data"]["items"][0]["description"] == "知名游资"


class TestHotHistoryEndpoint:
    def test_multi_day_curve(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/hot-history", params={"code": "000001"})
        items = r.json()["data"]["items"]
        assert len(items) == 2
        assert items[0]["trade_date"] == "2026-08-14"

    def test_unknown_404(self, client):
        _, c = client
        r = c.get("/api/v1/stocks/hot-history", params={"code": "999999"})
        assert r.status_code == 404
