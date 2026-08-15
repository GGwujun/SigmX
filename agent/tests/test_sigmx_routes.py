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
        store._conn.executemany(
            "INSERT OR REPLACE INTO fund_flow_daily "
            "(code, trade_date, main_net, super_net, large_net, mid_net, small_net, net_amount, turnover, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("000001", "2026-08-14", 0.85, 0.42, 0.43, -0.2, -0.15, 0.85, 2.3)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO stock_capital_flow "
            "(code, trade_date, period, m_in, m_out, m_net, r_in, r_out, r_net, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("000001", "2026-08-14", 1, 1.2, 0.4, 0.8, 0.5, 0.3, 0.2),
             ("000001", "2026-08-14", 5, 3.2, 1.4, 1.8, 1.5, 1.3, 0.2)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO stock_capital_rank "
            "(trade_date, rank_type, code, name, main_net, change_pct, updated_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            [("2026-08-14", "inflow", "000001", "平安银行", 0.8, 3.9),
             ("2026-08-14", "outflow", "000002", "万科A", -1.2, -2.1)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO northbound_flow "
            "(trade_date, time, hgt_yi, sgt_yi, updated_at) "
            "VALUES (?,?,?,?,datetime('now'))",
            [("2026-08-14", "09:31", 1.2, 0.8), ("2026-08-14", "15:00", 3.4, 2.2)],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO zt_pool "
            "(trade_date, code, name, price, pct, limit_days, first_seal, seal_fund, break_times, industry, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("2026-08-14", "000001", "平安银行", 10.6, 10.0, 2, "09:31:05", 1.5e8, 0, "银行"),
             ("2026-08-14", "600519", "贵州茅台", 1800.0, 10.0, 5, "09:25:00", 8.2e8, 1, "白酒")],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO dragon_tiger "
            "(code, trade_date, name, close, rise_rate, net_amt, buy_amt, sell_amt, extra_json, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            [("000001", "2026-08-14", "平安银行", 10.6, 10.0, 0.85, 1.2, 0.35,
              '{"seat_buy": ["机构专用"]}')],
        )
        store._conn.executemany(
            "INSERT OR REPLACE INTO hot_list "
            "(trade_date, code, name, rank, hot_value, change_pct, source, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            [("2026-08-14", "000001", "平安银行", 1, 9.9e5, 10.0, "ths")],
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO market_regime "
            "(trade_date, regime, confidence, bull_score, bear_score, strong_trend, indicators_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            ("2026-08-14", "bull", 0.72, 65.0, 20.0, 1, '{"broad_breadth": 0.61}'),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO financial_snapshot "
            "(code, trade_date, eps, bvps, roe, profit, income, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            ("000001", "2026-06-30", 1.23, 18.5, 9.2, 4.5e10, 1.2e11),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO financial_statement "
            "(code, report_date, report_type, payload_json, updated_at) "
            "VALUES (?,?,?,?,datetime('now'))",
            ("000001", "2026-06-30", "lrb", '{"revenue": 100}'),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO eps_forecast "
            "(code, trade_date, year, count, mean_eps, max_eps, updated_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            ("000001", "2026-08-14", "2026", 12, 2.1, 2.5),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO margin_trading "
            "(code, trade_date, rzye, rzrqye, updated_at) "
            "VALUES (?,?,?,?,datetime('now'))",
            ("000001", "2026-08-14", 5.1e9, 5.3e9),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO block_trade "
            "(code, trade_date, price, close, premium_pct, vol, amount, buyer, seller, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            ("000001", "2026-08-14", 10.3, 10.6, -2.8, 1e6, 1.03e7, "机构A", "机构B"),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO holder_num "
            "(code, end_date, holder_num, change_num, change_ratio, updated_at) "
            "VALUES (?,?,?,?,?,datetime('now'))",
            ("000001", "2026-06-30", 520000, -15000, -2.8),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO dividend_history "
            "(code, ex_date, bonus_rmb, transfer_ratio, bonus_ratio, updated_at) "
            "VALUES (?,?,?,?,?,datetime('now'))",
            ("000001", "2026-07-08", 0.25, 0.0, 0.3),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO fund_premium_snapshot "
            "(code, trade_date, name, type, price, nav, premium_rate, signal, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            ("501018", "2026-08-14", "南方原油", "LOF", 1.55, 1.42, 9.15, "溢价"),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO arbitrage_signal "
            "(code, trade_date, name, signal_type, premium_rate, z_score, status, updated_at) "
            "VALUES (?,?,?,?,?,?,?,datetime('now'))",
            ("501018", "2026-08-14", "南方原油", "PREMIUM", 9.15, 2.8, "ACTIVE"),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO etf_share_size "
            "(code, trade_date, name, total_share, total_size, nav, updated_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            ("510050", "2026-08-14", "50ETF", 1.2e11, 3.6e10, 3.05),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO option_chain "
            "(underlying, trade_date, month, code, call_put, strike, iv, open_interest, volume, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            ("510050", "2026-08-14", "2609", "10005012", "C", 3.0, 0.18, 5600, 1200),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO market_stage_snapshot "
            "(trade_date, stage, payload_json, source_tables, updated_at) "
            "VALUES (?,?,?,?,datetime('now'))",
            ("2026-08-14", "premarket", '{"headline": "ok"}', "premarket_news"),
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


class TestFundFlow:
    def test_fund_flow_history(self, client):
        r = client.get("/api/v1/stocks/fund-flow", params={"code": "000001"})
        body = r.json()
        assert body["data"]["items"][0]["main_net"] == 0.85

    def test_fund_flow_unknown_404(self, client):
        r = client.get("/api/v1/stocks/fund-flow", params={"code": "999999"})
        assert r.status_code == 404


class TestCapitalFlow:
    def test_capital_flow_all_periods(self, client):
        r = client.get("/api/v1/stocks/capital-flow", params={"codes": "000001"})
        body = r.json()
        assert body["data"]["count"] == 2

    def test_capital_flow_period_filter(self, client):
        r = client.get("/api/v1/stocks/capital-flow", params={"codes": "000001", "period": 1})
        body = r.json()
        assert body["data"]["count"] == 1
        assert body["data"]["items"][0]["period"] == 1

    def test_capital_flow_bad_period_400(self, client):
        r = client.get("/api/v1/stocks/capital-flow", params={"codes": "000001", "period": 7})
        assert r.status_code == 400


class TestCapitalRank:
    def test_inflow_rank_desc(self, client):
        r = client.get("/api/v1/stocks/capital-rank")
        body = r.json()
        item = body["data"]["items"][0]
        assert item["code"] == "000001"
        assert item["rank"] == 1

    def test_bad_rank_type_400(self, client):
        r = client.get("/api/v1/stocks/capital-rank", params={"rank_type": "sideways"})
        assert r.status_code == 400


class TestNorthbound:
    def test_series_ordered_by_time(self, client):
        r = client.get("/api/v1/northbound/flow")
        body = r.json()
        items = body["data"]["items"]
        assert len(items) == 2
        assert items[0]["time"] < items[1]["time"]
        assert items[1]["hgt_yi"] == 3.4


class TestLimitPool:
    def test_zt_pool_sorted_by_limit_days(self, client):
        r = client.get("/api/v1/stocks/limit-pool", params={"pool_type": "zt"})
        body = r.json()
        items = body["data"]["items"]
        assert len(items) == 2
        assert items[0]["limit_days"] >= items[1]["limit_days"]
        assert items[0]["code"] == "600519"

    def test_bad_pool_type_400(self, client):
        r = client.get("/api/v1/stocks/limit-pool", params={"pool_type": "spicy"})
        assert r.status_code == 400

    def test_unknown_pool_404(self, client):
        r = client.get("/api/v1/stocks/limit-pool", params={"pool_type": "dt"})
        assert r.status_code == 404


class TestDragonTiger:
    def test_rows_with_extra_expanded(self, client):
        r = client.get("/api/v1/dragon-tiger")
        body = r.json()
        item = body["data"]["items"][0]
        assert item["net_amt"] == 0.85
        assert item["seat_buy"] == ["机构专用"]
        assert "extra_json" not in item


class TestHotList:
    def test_ordered_by_rank(self, client):
        r = client.get("/api/v1/hot-list")
        body = r.json()
        assert body["data"]["items"][0]["rank"] == 1


class TestMarketRegime:
    def test_regime_with_indicators(self, client):
        r = client.get("/api/v1/market/regime")
        body = r.json()
        data = body["data"]
        assert data["regime"] == "bull"
        assert data["indicators"]["broad_breadth"] == 0.61


class TestFundamentals:
    def test_financial_snapshot(self, client):
        r = client.get("/api/v1/stocks/financial-snapshot", params={"codes": "000001"})
        item = r.json()["data"]["items"][0]
        assert item["eps"] == 1.23
        assert item["roe"] == 9.2

    def test_financial_statement_parses_payload(self, client):
        r = client.get("/api/v1/stocks/financial-statement", params={"code": "000001"})
        item = r.json()["data"]["items"][0]
        assert item["payload"]["revenue"] == 100

    def test_financial_statement_bad_type_400(self, client):
        r = client.get("/api/v1/stocks/financial-statement",
                       params={"code": "000001", "report_type": "xyz"})
        assert r.status_code == 400

    def test_eps_forecast(self, client):
        r = client.get("/api/v1/stocks/eps-forecast", params={"code": "000001"})
        assert r.json()["data"]["items"][0]["mean_eps"] == 2.1

    def test_margin(self, client):
        r = client.get("/api/v1/stocks/margin")
        assert r.json()["data"]["items"][0]["rzye"] == 5.1e9

    def test_block_trade(self, client):
        r = client.get("/api/v1/stocks/block-trade")
        item = r.json()["data"]["items"][0]
        assert item["buyer"] == "机构A"
        assert item["premium_pct"] == -2.8

    def test_holder_num(self, client):
        r = client.get("/api/v1/stocks/holder-num", params={"code": "000001"})
        assert r.json()["data"]["items"][0]["change_ratio"] == -2.8

    def test_dividends(self, client):
        r = client.get("/api/v1/stocks/dividends", params={"code": "000001"})
        assert r.json()["data"]["items"][0]["bonus_rmb"] == 0.25


class TestFundsEtf:
    def test_premium_sorted_by_abs(self, client):
        r = client.get("/api/v1/funds/premium")
        body = r.json()
        assert body["data"]["items"][0]["premium_rate"] == 9.15

    def test_premium_type_filter(self, client):
        r = client.get("/api/v1/funds/premium", params={"type": "ETF"})
        assert r.status_code == 404

    def test_arbitrage_signals(self, client):
        r = client.get("/api/v1/funds/arbitrage-signals")
        item = r.json()["data"]["items"][0]
        assert item["signal_type"] == "PREMIUM"
        assert item["z_score"] == 2.8

    def test_bad_signal_status_400(self, client):
        r = client.get("/api/v1/funds/arbitrage-signals", params={"status": "MAYBE"})
        assert r.status_code == 400

    def test_share_size(self, client):
        r = client.get("/api/v1/etf/share-size")
        assert r.json()["data"]["items"][0]["code"] == "510050"


class TestMarketStats:
    def test_option_chain(self, client):
        r = client.get("/api/v1/option-chain")
        item = r.json()["data"]["items"][0]
        assert item["call_put"] == "C"
        assert item["strike"] == 3.0

    def test_option_chain_call_filter(self, client):
        r = client.get("/api/v1/option-chain", params={"call_put": "P"})
        assert r.status_code == 404

    def test_stage_snapshot(self, client):
        r = client.get("/api/v1/market/stage-snapshot")
        item = r.json()["data"]["items"][0]
        assert item["stage"] == "premarket"
        assert item["payload"]["headline"] == "ok"
