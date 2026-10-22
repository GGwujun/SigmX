# -*- coding: utf-8 -*-
"""产业信号资产：确定性卡口分类 + 行业温度 + fetcher/插件挂载，全程无网络。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research_pipeline.fetchers import FETCHERS, fetch_dataset
from src.research_pipeline.industry_signals import (
    CHOKEPOINT_RULES,
    classify_announcement,
    industry_temperature,
)
from src.research_pipeline.plugins.a_stock import a_stock_plugin


class _FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def get_announcements(self, code, days=90):
        return self._rows


# ---------------- classify_announcement ----------------

@pytest.mark.unit
def test_classify_positive_hits() -> None:
    assert classify_announcement("公司产品提价，发布调价函") == ["涨价"]
    assert "扩产" in classify_announcement("募投项目如期投产，产能释放")
    assert classify_announcement("公司被列入实体清单") == ["管制制裁"]


@pytest.mark.unit
def test_classify_clause_level_negatives() -> None:
    # negatives 在同一子句内判定：并列事项不互相否决
    assert classify_announcement("未涨价") == []
    assert classify_announcement("签订重大合同；产品未涨价") == ["订单合同"]
    # 子句级恢复词挡住停产
    assert classify_announcement("产线停产") == ["减产停产"]
    assert classify_announcement("产线恢复生产") == []


@pytest.mark.unit
def test_classify_multiple_categories() -> None:
    hits = classify_announcement("签订长期协议并中标；新建产能投产")
    assert "订单合同" in hits and "扩产" in hits


@pytest.mark.unit
def test_classify_regex_context_constraint() -> None:
    # 「签订」必须跟销售/供货/采购等——裸「签订」不算订单
    assert classify_announcement("公司与对方签订备忘录") == []
    assert "订单合同" in classify_announcement("公司与客户签订销售合同")


@pytest.mark.unit
def test_classify_english_word_boundary() -> None:
    assert "供需" in classify_announcement("Chips sold out, lead time extends")
    assert classify_announcement("unsold output rises") == []  # sold 边界不误伤


@pytest.mark.unit
def test_classify_empty_and_noise() -> None:
    assert classify_announcement("") == []
    assert classify_announcement("关于召开2026年第一次临时股东大会的通知") == []


# ---------------- industry_temperature ----------------

@pytest.mark.unit
def test_temperature_strong_weak_neutral() -> None:
    assert industry_temperature("行业供不应求，多地缺货") == "强"
    assert industry_temperature("下游需求疲软，产能过剩") == "弱"
    assert industry_temperature("供不应求但部分环节过剩") == ""   # 互抵不给温度
    assert industry_temperature("今日晴") == ""


# ---------------- fetcher 挂载 ----------------

@pytest.mark.unit
def test_chokepoint_fetcher_filters_and_maps(tmp_path: Path) -> None:
    store = _FakeStore([
        {"code": "300750", "ann_date": "2026-10-20", "title": "公司产品提价",
         "ann_type": "其他", "url": "https://example.com/a"},
        {"code": "300750", "ann_date": "2026-10-19",
         "title": "关于召开临时股东大会的通知", "ann_type": "会议", "url": ""},
    ])
    rows, error = fetch_dataset(store, "chokepoint_events", "300750", None)
    assert error == ""
    assert rows == [{"ann_date": "2026-10-20", "title": "公司产品提价",
                     "categories": ["涨价"], "url": "https://example.com/a"}]


@pytest.mark.unit
def test_chokepoint_fetcher_empty_is_ok() -> None:
    rows, error = fetch_dataset(_FakeStore([]), "chokepoint_events", "300750", None)
    assert error == "" and rows == []      # 无命中 = empty 信封，不是故障
    assert "chokepoint_events" in FETCHERS


# ---------------- a_stock 插件挂载 ----------------

@pytest.mark.unit
def test_a_stock_risk_declares_chokepoint_dataset() -> None:
    datasets = a_stock_plugin.stage_datasets["risk"]
    assert "chokepoint_events" in datasets.optional
    schema = a_stock_plugin.stage_schemas["risk"]
    assert "chokepoint_events" in schema.properties
    assert "chokepoint_events" not in schema.required   # 可选，无命中不苛责
    sheet = a_stock_plugin.build_stage_prompt("risk", {"code": "300750"})
    assert "fetch/chokepoint_events.json" in sheet
    assert "chokepoint_events" in sheet                  # 产物 schema 提示也在


# ---------------- 端到端：分类行进证据链可被引用 ----------------

@pytest.mark.unit
def test_chokepoint_rows_become_citable_evidence(tmp_path: Path) -> None:
    """真实 fetcher 走 write_fetch：命中行拿到确定性证据 id（ev-chokepoint_events-N）。"""
    from src.research_pipeline.fetchers import write_fetch

    store = _FakeStore([
        {"code": "300750", "ann_date": "2026-10-20",
         "title": "募投项目投产并签订销售合同", "ann_type": "其他",
         "url": "https://example.com/a"},
    ])
    rows, error = fetch_dataset(store, "chokepoint_events", "300750", None)
    entry = write_fetch(tmp_path, "chokepoint_events",
                        {"code": "300750", "trade_date": None}, rows, error, "risk")
    assert entry.status == "ok" and entry.rows == 1
    envelope = json.loads((tmp_path / "fetch" / "chokepoint_events.json")
                          .read_text(encoding="utf-8"))
    ev = envelope["evidence"][0]
    assert ev["id"] == "ev-chokepoint_events-0"
    assert set(ev["data"]["categories"]) == {"扩产", "订单合同"}
