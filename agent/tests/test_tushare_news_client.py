"""tushare 资讯页解析器测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.data.tushare_news_client import CN_TZ, fetch_tushare_news, parse_news_page

SAMPLE_HTML = """
<div id="news_7*24全球直播" class="news_data">
  <div class="none_class news_item">
    <div class="news_datetime">16:13</div>
    <div class="news_content">【美移民与海关执法局将采购机器狗用于执法】28日,据美国方面消息。</div>
  </div>
  <div class="none_class news_item">
    <div class="news_datetime">15:57</div>
    <div class="news_content">没有书名号标题的纯内容快讯,按内容截断生成标题。</div>
  </div>
  <div class="news_day news_item"><img src="/static/frontend/images/clock.png" />8月28日</div>
  <div class="none_class news_item">
    <div class="news_datetime">23:58</div>
    <div class="news_content">【*ST元道:收到深交所终止上市事先告知书】*ST元道(301139.SZ)公告称。</div>
  </div>
</div>
"""


def test_parse_extracts_items_titles_and_dates() -> None:
    now = datetime(2026, 8, 29, 17, 0, tzinfo=CN_TZ)

    items = parse_news_page(SAMPLE_HTML, now=now)

    assert len(items) == 3
    assert items[0]["title"] == "美移民与海关执法局将采购机器狗用于执法"
    assert items[0]["snippet"].startswith("【美移民")
    # 分隔行之前:视为当天(8月29日)
    assert "29 Aug 2026 16:13" in items[0]["published"]
    # 无书名号:取内容前 40 字
    assert items[1]["title"].startswith("没有书名号标题")
    # 分隔行之后:使用分隔行日期(8月28日)
    assert "28 Aug 2026 23:58" in items[2]["published"]


def test_parse_rolls_year_back_for_future_dates() -> None:
    html = '<div class="news_day news_item"><img/>12月31日</div>' \
           '<div class="none_class news_item"><div class="news_datetime">23:59</div>' \
           '<div class="news_content">【跨年】年末快讯。</div></div>'
    now = datetime(2027, 1, 1, 8, 0, tzinfo=CN_TZ)

    items = parse_news_page(html, now=now)

    assert "31 Dec 2026 23:59" in items[0]["published"]


def test_parse_respects_limit() -> None:
    assert len(parse_news_page(SAMPLE_HTML, limit=2, now=datetime(2026, 8, 29, tzinfo=CN_TZ))) == 2


def test_fetch_requires_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUSHARE_COOKIE", raising=False)
    with pytest.raises(RuntimeError, match="TUSHARE_COOKIE"):
        fetch_tushare_news("cls")


def test_fetch_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="不支持"):
        fetch_tushare_news("unknown-src")
