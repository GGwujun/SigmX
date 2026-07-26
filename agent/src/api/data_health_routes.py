"""Data-source health check — ``GET /data-health``.

Each configured upstream (mootdx / akshare / RSSHub / overseas proxy) is probed
with a short timeout and reported as ``{ok, latency_ms, detail}``. This is the
single pane of glass for "why can't the Aliyun deployment pull data": instead of
guessing which source 403'd or timed out, the operator opens the settings page
and sees green/red per source.

All probes are bounded (short timeouts) and never raise — a failing source
returns ``ok=False`` with a short error string, not an HTTP error. The endpoint
is admin-gated (mounted with ``require_admin``).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

import requests
from fastapi import Depends, FastAPI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 6  # seconds per source — keep the whole endpoint snappy


class SourceHealth(BaseModel):
    name: str
    ok: bool
    latency_ms: int
    detail: str


class DataHealthReport(BaseModel):
    sources: list[SourceHealth]
    summary_ok: int
    summary_total: int


def _probe(name: str, fn: Callable[[], Any]) -> SourceHealth:
    """Run a probe fn, capture ok/latency/error. Never raises."""
    t0 = time.monotonic()
    try:
        result = fn()
        ms = int((time.monotonic() - t0) * 1000)
        detail = result if isinstance(result, str) else "ok"
        return SourceHealth(name=name, ok=True, latency_ms=ms, detail=detail)
    except Exception as exc:  # noqa: BLE001 — health probes swallow everything
        ms = int((time.monotonic() - t0) * 1000)
        msg = str(exc) or exc.__class__.__name__
        return SourceHealth(name=name, ok=False, latency_ms=ms, detail=msg[:200])


def _probe_mootdx() -> str:
    from src.data.mootdx_helper import pick_server, last_picked_server

    server = pick_server(timeout=_PROBE_TIMEOUT) or last_picked_server()
    if server is None:
        raise RuntimeError("no reachable TDX server (all candidates failed)")
    # Actually exercise the client so "factory built" != "can read quotes".
    from src.data.mootdx_helper import get_quotes

    client = get_quotes(timeout=_PROBE_TIMEOUT)
    # NOTE: ``markets()`` is only on ExtQuotes, not StdQuotes (removed in mootdx 0.9.x).
    # Use stock_count(market=0) instead — it exercises the socket without needing a symbol.
    count = client.stock_count(market=0)
    if not count:
        raise RuntimeError("connected but stock_count(0) returned empty")
    return f"server {server[0]}:{server[1]}"


def _probe_akshare() -> str:
    import akshare as ak

    # A cheap, stable call: latest A-share trading calendar / a tiny spot pull.
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot_em returned empty")
    return f"{len(df)} A-share rows"


def _probe_rsshub() -> str:
    base = os.getenv("RSSHUB_URL", "http://localhost:1200").rstrip("/")

    # Graceful when RSSHub is not configured. The desktop client ships without
    # a local RSSHub container, and most desktop users won't set RSSHUB_URL —
    # probing localhost:1200 would then always fail and paint the health panel
    # red for an *optional* feature. Make that explicit so users don't panic.
    if not base or base in {"http://localhost:1200", "http://127.0.0.1:1200"}:
        raise RuntimeError(
            "RSSHub 未配置 — 新闻聚合功能关闭(可选)。"
            "在 Settings → 数据连接 填写 RSSHub 地址即可启用"
        )

    resp = requests.get(f"{base}/healthz", timeout=_PROBE_TIMEOUT)
    # Some RSSHub versions expose /healthz, others only /health; accept either.
    if resp.status_code == 404:
        resp = requests.get(f"{base}/health", timeout=_PROBE_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"RSSHub HTTP {resp.status_code}")
    return base


def _probe_overseas_proxy() -> str:
    proxy = os.getenv("OVERSEAS_PROXY_URL", "").strip()
    if not proxy:
        raise RuntimeError("OVERSEAS_PROXY_URL not configured (海外代理未配置)")
    secret = os.getenv("PROXY_SECRET", "").strip()
    resp = requests.get(
        f"{proxy.rstrip('/')}/health",
        headers={"X-Proxy-Key": secret} if secret else {},
        timeout=_PROBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"proxy HTTP {resp.status_code}")
    return proxy


def _probe_tpdog() -> str:
    """Probe TPDog (托普量化) HTTPS data source. Skips cleanly when no token."""
    from src.data.tpdog_client import TpdogError, TpdogNotConfiguredError, call

    try:
        # Cheapest live call: 1 积分, 30 次/秒 — current-year trading days.
        call("trading_day/year", year="2026")
        return "token ok"
    except TpdogNotConfiguredError:
        raise RuntimeError("TPDOG_TOKEN 未配置")
    except TpdogError as exc:
        raise RuntimeError(str(exc))


def _probe_tushare() -> str:
    """Probe Tushare Pro REST API. Returns token status + account level."""
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts

    pro = ts.pro_api(token)
    # Cheapest call: query a single known stock to verify token validity.
    df = pro.daily(ts_code="000001.SZ", start_date="20260101", end_date="20260101")
    if df is None or df.empty:
        # Token might be valid but no data for that date — try trade_cal instead.
        df = pro.trade_cal(exchange="SSE", start_date="20260101", end_date="20260101")
        if df is None:
            raise RuntimeError("tushare API 无响应")
    return f"token ok ({len(df)} rows)"


def _probe_baostock() -> str:
    """Probe BaoStock free A-share data source."""
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    try:
        # Query a recent date range (last 5 trading days) to find a valid row.
        rs = bs.query_history_k_data_plus(
            "sh.000001", "date,close",
            start_date="2026-07-01", end_date="2026-07-24",
        )
        if rs.error_code != "0":
            raise RuntimeError(rs.error_msg)
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            raise RuntimeError("baostock query returned no rows")
        latest = rows[-1]
        return f"{len(rows)} rows, latest={latest[0]} close={latest[1]}"
    finally:
        bs.logout()


def _probe_yfinance() -> str:
    """Probe Yahoo Finance (yfinance) for overseas market data."""
    import yfinance as yf

    # Cheapest call: 1-day history for a liquid US ticker.
    ticker = yf.Ticker("AAPL")
    df = ticker.history(period="1d")
    if df is None or df.empty:
        raise RuntimeError("yfinance returned empty (possibly rate-limited)")
    close = df["Close"].iloc[-1]
    return f"AAPL close={close:.2f}"


def _probe_local_db() -> str:
    """Probe local market.db — integrity check + data freshness."""
    from pathlib import Path

    db_path = Path(os.getenv("VIBE_TRADING_MARKET_DB_PATH",
                   Path.home() / ".vibe-trading" / "market.db"))
    if not db_path.exists():
        raise RuntimeError(f"market.db not found: {db_path}")

    import sqlite3

    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        # Integrity check
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError(f"DB integrity: {row[0] if row else 'no response'}")

        # Latest trade date
        cur = conn.execute(
            "SELECT MAX(trade_date) FROM bars_daily WHERE trade_date IS NOT NULL"
        )
        latest = cur.fetchone()[0]
        if not latest:
            raise RuntimeError("bars_daily 无数据")

        # Row counts for key tables
        bars = conn.execute("SELECT COUNT(*) FROM bars_daily").fetchone()[0]
        size_mb = db_path.stat().st_size / (1024 * 1024)
        return f"latest={latest}, {bars} bars, {size_mb:.0f}MB"
    finally:
        conn.close()


def _probe_tencent() -> str:
    """Probe Tencent Finance real-time quote API (优先用，不封IP)."""
    import requests as r

    resp = r.get(
        "https://qt.gtimg.cn/q=sh000001",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_PROBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"腾讯 HTTP {resp.status_code}")
    text = resp.text
    if not text or "000001" not in text:
        raise RuntimeError("腾讯返回空或格式异常")
    return "qt.gtimg.cn ok"


def _probe_sina() -> str:
    """Probe Sina Finance real-time index API (备用源：指数/财报/期权)."""
    import requests as r

    resp = r.get(
        "https://hq.sinajs.cn/list=sh000001",
        headers={"Referer": "https://finance.sina.com.cn/"},
        timeout=_PROBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"新浪 HTTP {resp.status_code}")
    if resp.encoding and resp.encoding.lower() in ("gbk", "gb2312"):
        text = resp.content.decode("gbk", errors="replace")
    else:
        text = resp.text
    if not text or "000001" not in text:
        raise RuntimeError("新浪返回空或格式异常")
    return "hq.sinajs.cn ok"


def _probe_baidu() -> str:
    """Probe Baidu Stock K-line API (独立K线源，自带MA5/10/20)."""
    import requests as r

    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": "sh000001", "ktype": "1",
    }
    resp = r.get(
        "https://finance.pae.baidu.com/selfselect/getstockquotation",
        params=params,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.finance-web.v1+json",
            "Origin": "https://gushitong.baidu.com",
            "Referer": "https://gushitong.baidu.com/",
        },
        timeout=_PROBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"百度 HTTP {resp.status_code}")
    data = resp.json()
    # ResultCode 0 = success; 百度返回字符串 "0"，必须字符串比较，否则 "0" != 0 永远误判。
    if str(data.get("ResultCode")) != "0":
        raise RuntimeError(f"百度 ResultCode={data.get('ResultCode')}")
    return "finance.pae.baidu.com ok"


def _probe_cninfo() -> str:
    """Probe Cninfo (巨潮资讯) announcement API (公告/互动易)."""
    import requests as r

    resp = r.post(
        "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        json={"pageNum": 1, "pageSize": 1, "column": "szse", "tabName": "fulltext"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_PROBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"巨潮 HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("巨潮返回格式异常")
    return "cninfo.com.cn ok"


def register_data_health_routes(app: FastAPI) -> None:
    """Mount ``GET /data-health`` (admin only)."""
    from src.api.auth_routes import require_admin

    @app.get(
        "/data-health",
        response_model=DataHealthReport,
        dependencies=[Depends(require_admin)],
    )
    async def data_health() -> DataHealthReport:
        probes = [
            _probe("mootdx (A股行情)", _probe_mootdx),
            _probe("腾讯 (实时行情)", _probe_tencent),
            _probe("百度 (K线)", _probe_baidu),
            _probe("tushare (A股高级数据)", _probe_tushare),
            _probe("baostock (免费A股)", _probe_baostock),
            _probe("akshare (全球/宏观)", _probe_akshare),
            _probe("tpdog (托普量化)", _probe_tpdog),
            _probe("新浪 (指数/财报)", _probe_sina),
            _probe("巨潮 (公告)", _probe_cninfo),
            _probe("yfinance (海外行情)", _probe_yfinance),
            _probe("RSSHub (新闻聚合)", _probe_rsshub),
            _probe("overseas_proxy (海外源)", _probe_overseas_proxy),
            _probe("本地数据库", _probe_local_db),
        ]
        return DataHealthReport(
            sources=probes,
            summary_ok=sum(1 for p in probes if p.ok),
            summary_total=len(probes),
        )
