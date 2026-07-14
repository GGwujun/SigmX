from __future__ import annotations

import ast
import json
from pathlib import Path

from src.data import astock_client as client


def test_stock_news_payload_accepts_direct_article_list() -> None:
    payload = {
        "result": {
            "cmsArticleWebOld": [
                {
                    "title": "<em>贵州茅台</em>公告",
                    "content": "<p>正文</p>",
                    "date": "2026-07-14 10:00:00",
                    "mediaName": "测试媒体",
                    "url": "https://example.test/news/1",
                }
            ]
        }
    }

    rows = client._parse_eastmoney_stock_news_payload(payload)

    assert rows == [
        {
            "title": "贵州茅台公告",
            "summary": "正文",
            "date": "2026-07-14 10:00:00",
            "source": "测试媒体",
            "url": "https://example.test/news/1",
        }
    ]


def test_baidu_kline_payload_treats_empty_result_list_as_unavailable() -> None:
    assert client._parse_baidu_kline_payload({"Result": []}) == {
        "keys": [],
        "rows": [],
    }


def test_baidu_kline_payload_splits_market_data_rows() -> None:
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "close", "ma5avgprice"],
                "marketData": "20260711,1400,1398;20260714,1410,1402",
            }
        }
    }

    assert client._parse_baidu_kline_payload(payload) == {
        "keys": ["time", "close", "ma5avgprice"],
        "rows": ["20260711,1400,1398", "20260714,1410,1402"],
    }


def test_ths_hot_reason_keeps_missing_numbers_unknown() -> None:
    row = client._normalize_ths_hot_reason_item(
        {
            "code": "605133",
            "name": "嵘泰股份",
            "reason": "人形机器人",
            "date": "2026-07-14",
            "market": 17,
        }
    )

    assert row["change_pct"] is None
    assert row["turnover"] is None
    assert row["amount"] is None
    assert row["close"] is None


def test_ths_hot_list_maps_heat_price_change_and_serializable_tags() -> None:
    row = client._normalize_ths_hot_list_item(
        {
            "order": 1,
            "code": "002354",
            "name": "天娱数科",
            "rate": 567323.0,
            "rise_and_fall": 9.98,
            "hot_rank_chg": 3,
            "tag": {"concept_tag": ["AI视频", "虚拟数字人"]},
        }
    )

    assert row["hot_value"] == 567323.0
    assert row["change_pct"] == 9.98
    assert row["rank_change"] == 3
    assert json.loads(row["tags"])["concept_tag"] == ["AI视频", "虚拟数字人"]


def test_lockup_payload_uses_v34_field_names() -> None:
    result = client._parse_lockup_rows(
        [
            {
                "FREE_DATE": "2026-07-20 00:00:00",
                "FREE_SHARES_TYPE": "首发原股东限售股份",
                "FREE_SHARES": 100.0,
                "ABLE_FREE_SHARES": 80.0,
                "FREE_RATIO": 0.012,
            }
        ],
        trade_date="2026-07-14",
    )

    assert result["history"] == []
    assert result["upcoming"] == [
        {
            "date": "2026-07-20",
            "type": "首发原股东限售股份",
            "shares": 100.0,
            "able_shares": 80.0,
            "ratio": 0.012,
        }
    ]


def test_client_has_no_duplicate_top_level_function_definitions() -> None:
    path = Path(client.__file__)
    module = ast.parse(path.read_text(encoding="utf-8"))
    names = [
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert len(names) == len(set(names))
