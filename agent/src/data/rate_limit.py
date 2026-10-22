# -*- coding: utf-8 -*-
"""统一限频登记表（线 A）：market_sync 各数据源的等待预算集中一处。

此前限频值散在 market_sync.py 各函数里（62 分钟配额重试 / 30 分钟数据
延迟 / 62 秒逐调用 / 0.05~0.6 秒 pacing），线上调一次参要改代码重发镜像。
本模块把它们统一登记：**默认值与历史行为完全一致**，但全部可用环境变量
覆盖，线上调参改 env 重启即可：

- ``SIGMX_RATE_SCALE``：全局缩短倍数（0<scale≤1，等比缩放全部等待，
  测试用它把 62 分钟缩成毫秒级；>1 拒绝，防止有人把等待放大）
- ``SIGMX_RATE_<名称大写>``：单项覆盖（优先于 SCALE），如
  ``SIGMX_RATE_TUSHARE_DAILY_BASIC_QUOTA_RETRY=1800``

语义分两类：**限频**（pacing/配额，源端拒绝我们）与**数据延迟**（源端
还没发布，等多久都不是我们的错）。后者单列 DATA_DELAYS，避免把
「数据没出」误当「请求太快」去重试打爆对方。

调用约定：market_sync 里写 ``time.sleep(rate_seconds("name"))``——
经 market_sync 自己的 ``time`` 模块引用睡，现有测试桩
（monkeypatch ms.time.sleep）继续生效，不引入第二sleep通道。
"""

from __future__ import annotations

import os

# 限频等待（秒）：pacing=逐调用间隔，quota_retry=命中配额后的等待
RATE_WAITS: dict[str, float] = {
    "tpdog_pacing": 0.05,                    # tpdog 上限 30 calls/s
    "tushare_index_pacing": 62.0,            # index_daily 1 req/min（首调用不睡）
    "tushare_daily_basic_quota_retry": 62 * 60,   # daily_basic 1 次/小时，超限等下个窗口
    "tushare_daily_basic_empty_retry": 60.0,      # 空结果补试前的礼貌等待
    "akshare_capital_pacing": 0.6,           # 东财资金流接口逐股间隔（原 _AKSHARE_CAPITAL_SLEEP）
    "eastmoney_clist_paging": 0.15,          # clist 分页翻页间隔
    "eps_forecast_pacing": 0.3,              # 盈利预测逐股间隔
    "financial_snapshot_pacing": 0.1,        # 财务快照逐股间隔
    "yfinance_retry": 10.0,                  # yfinance 失败后重试等待
}

# 数据发布延迟（秒）：等数据到位，不是限频——不要用它去做重试风暴
DATA_DELAYS: dict[str, float] = {
    "tpdog_etf_data_delay": 30 * 60,         # ETF 日线首拉 0 行：tpdog 数据未发布
}

_ALL_WAITS: dict[str, float] = {**RATE_WAITS, **DATA_DELAYS}

_SCALE_ENV = "SIGMX_RATE_SCALE"
_PREFIX = "SIGMX_RATE_"


def _scale() -> float:
    raw = os.getenv(_SCALE_ENV, "").strip()
    if not raw:
        return 1.0
    try:
        factor = float(raw)
    except ValueError:
        return 1.0
    if factor <= 0 or factor > 1:
        return 1.0    # 只允许缩短，不允许放大
    return factor


def rate_seconds(name: str) -> float:
    """取某项等待秒数：单项 env 覆盖 > 全局 SCALE 等比缩放 > 默认值。

    名称不存在直接 KeyError——限频名拼错应该当场炸，而不是默默睡 0 秒。
    """
    if name not in _ALL_WAITS:
        raise KeyError(f"未知限频项: {name!r}（可用: {', '.join(sorted(_ALL_WAITS))}）")
    override = os.getenv(_PREFIX + name.upper(), "").strip()
    if override:
        try:
            return max(float(override), 0.0)
        except ValueError:
            pass
    return _ALL_WAITS[name] * _scale()
