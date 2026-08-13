"""Parse-logic tests for the "dead code" backup sources (data-source-plan §期1).

These astock_client functions are implemented but not yet wired into the
market_sync fallback chains, so they had no coverage. These tests verify their
parsing is correct against fixture responses so that wiring them later is low-
risk. Network is mocked — no real requests are made.
"""

from __future__ import annotations

import json
from unittest import mock

from src.data import astock_client as client


def _em_response(payload: dict) -> mock.MagicMock:
    r = mock.MagicMock()
    r.json.return_value = payload
    return r


# ---- eastmoney_fund_flow_minute (em_get) ----


def test_fund_flow_minute_parses_klines() -> None:
    # kline format: time,main_net,small_net,mid_net,large_net,super_net,+1 trailing field.
    payload = {"data": {"klines": [
        "2026-08-14 09:31,100.5,20.0,30.0,40.0,10.5,0",
        "2026-08-14 09:32,-50,5,-,-,15,0",
    ]}}
    with mock.patch.object(client, "em_get", return_value=_em_response(payload)):
        rows = client.eastmoney_fund_flow_minute("600519")
    assert len(rows) == 2
    assert rows[0]["time"] == "2026-08-14 09:31"
    assert rows[0]["main_net"] == 100.5
    # "-" placeholders become 0.
    assert rows[1]["large_net"] == 0
    assert rows[1]["super_net"] == 15


def test_fund_flow_minute_returns_empty_on_error() -> None:
    with mock.patch.object(client, "em_get", side_effect=RuntimeError("boom")):
        assert client.eastmoney_fund_flow_minute("000001") == []


# ---- eastmoney_global_news (em_get) ----


def test_global_news_maps_and_truncates_summary() -> None:
    payload = {"data": {"fastNewsList": [
        {"title": "加息", "summary": "x" * 300, "showTime": "12:00", "code": "n1"},
    ]}}
    with mock.patch.object(client, "em_get", return_value=_em_response(payload)):
        news = client.eastmoney_global_news(page_size=5)
    assert len(news) == 1
    assert news[0]["title"] == "加息"
    assert len(news[0]["summary"]) == 200  # truncated to 200 chars


def test_global_news_empty_when_no_list() -> None:
    with mock.patch.object(client, "em_get", return_value=_em_response({"data": {}})):
        assert client.eastmoney_global_news() == []


# ---- eastmoney_concept_blocks (em_get) ----


def test_concept_blocks_parses_boards_and_tags() -> None:
    payload = {"data": {"diff": [
        {"f14": "白酒", "f12": "BK0477", "f3": 2.35, "f128": "贵州茅台"},
        {"f14": "MSCI", "f12": "BK0901", "f3": -0.5, "f128": "宁德时代"},
    ]}}
    with mock.patch.object(client, "em_get", return_value=_em_response(payload)):
        result = client.eastmoney_concept_blocks("600519")
    assert result["total"] == 2
    assert result["boards"][0]["name"] == "白酒"
    assert "白酒" in result["concept_tags"]


def test_concept_blocks_empty_on_error() -> None:
    with mock.patch.object(client, "em_get", side_effect=RuntimeError("x")):
        result = client.eastmoney_concept_blocks("000001")
    assert result == {"total": 0, "boards": [], "concept_tags": []}


# ---- baidu_kline_with_ma (urllib) ----


def test_baidu_kline_parses_keys_and_rows() -> None:
    payload = json.dumps({"Result": {"newMarketData": {
        "keys": ["time", "ma5", "close"],
        "marketData": "09:30,10.0,10.5;09:31,10.1,10.6",
    }}}).encode()
    response = mock.MagicMock()
    response.__enter__.return_value = response  # support `with urlopen() as r`
    response.read.return_value = payload
    with mock.patch("urllib.request.urlopen", return_value=response):
        result = client.baidu_kline_with_ma("600519")
    assert result["keys"] == ["time", "ma5", "close"]
    assert result["rows"] == ["09:30,10.0,10.5", "09:31,10.1,10.6"]


def test_baidu_kline_unavailable_returns_empty() -> None:
    payload = json.dumps({"Result": None}).encode()
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = payload
    with mock.patch("urllib.request.urlopen", return_value=response):
        result = client.baidu_kline_with_ma("600519")
    assert result.get("rows", []) == []


# ---- limit_up_sentiment (depends on em_zt/zb/yzt pools) ----


def test_limit_up_sentiment_computes_rates() -> None:
    with mock.patch.object(client, "em_zt_pool", return_value=[
        {"code": "000001", "name": "A", "limit_days": 1},
        {"code": "000002", "name": "B", "limit_days": 3},
    ]), mock.patch.object(client, "em_zb_pool", return_value=[
        {"code": "000003", "name": "C"},  # 炸板
    ]), mock.patch.object(client, "em_yzt_pool", return_value=[
        {"code": "000001", "name": "A"}, {"code": "000002", "name": "B"},
    ]):
        sent = client.limit_up_sentiment("2026-08-14")
    # 2 涨停 + 1 炸板 → 炸板率 1/3
    assert sent["limit_up_count"] == 2
    assert sent["fail_count"] == 1
    assert sent["fail_rate"] == round(1 / 3 * 100, 2)
    assert sent["max_height"] == 3  # 最长连板 3


# ---- mootdx_f10 (tdx_client) ----


def test_mootdx_f10_returns_text() -> None:
    fake_client = mock.MagicMock()
    fake_client.F10.return_value = "公司概况：贵州茅台..."
    with mock.patch.object(client, "tdx_client", return_value=fake_client):
        text = client.mootdx_f10("600519", category="公司概况")
    assert "贵州茅台" in text
    fake_client.F10.assert_called_once_with(symbol="600519", name="公司概况")
