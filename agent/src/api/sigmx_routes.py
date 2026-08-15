"""
SigmX Market Data API（并入 vibe-trading）
Base: /api/v1   Timezone: Asia/Shanghai   Unit: 100M CNY (亿元)
只读访问 market.db；新闻走 RSSHub。
鉴权：Data Hub 模式下远程请求需 X-API-Key / 产品令牌（_data_hub_auth）。
"""
import ipaddress
import json
import logging
import math
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

DB_PATH = (
    os.environ.get("VIBE_TRADING_MARKET_DB_PATH")
    or os.path.expanduser("~/.vibe-trading/market.db")
)
RSSHUB_URL = os.environ.get("RSSHUB_URL", "http://rsshub:1200").rstrip("/")
TZ_SH = timezone(timedelta(hours=8))
ROWS_HARD_CAP = 2000

router = APIRouter(tags=["sigmx"])

# ---- API key auth (Data Hub) ----

def _is_loopback(request: Request) -> bool:
    """Check if the request originates from loopback.

    Also recognizes starlette's TestClient (``client=None`` scope with a
    ``testclient`` user-agent) so the auth gate stays testable across
    starlette/httpx versions that stopped populating ``request.client``.
    """
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    if not host and (request.headers.get("user-agent") or "").lower() == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def _data_hub_auth(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    api_key: str | None = Query(None, alias="api_key"),
) -> dict[str, object] | None:
    """API key authentication for /api/v1/* endpoints (Data Hub mode).

    - Non-Data-Hub deployments: always pass through (mode guard).
    - Loopback requests: pass through (no key needed).
    - Data Hub mode + non-loopback + no key: 401 (the public API requires a key).
    - Invalid key: 401.
    - Quota exhausted: 429.
    - Valid key with quota remaining: reserve one slot atomically, return sub.

    ``request.client.host`` reflects the real remote IP only when uvicorn runs
    with ``--proxy-headers`` and nginx forwards ``X-Forwarded-For``; otherwise a
    reverse proxy makes every request look loopback and this gate is bypassable.
    """
    if not _is_data_hub_enabled():
        return None

    if _is_loopback(request):
        return None

    # Product-token path (Task 6): accept a Bearer product access token before
    # the legacy X-API-Key path. If present and valid, enforce the plan's
    # datahub.daily_quota against product.db.usage_daily. If absent or invalid,
    # fall through to the legacy sx_ key logic unchanged.
    from src.product.datahub_auth import (
        acquire_product_quota,
        resolve_product_principal,
    )
    from src.product.store import ProductStore

    _product_store = ProductStore()
    principal = resolve_product_principal(request, _product_store)
    if principal is not None:
        if not acquire_product_quota(_product_store, principal):
            quota = principal.quota_daily
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily quota exceeded ({quota}/{quota}). Resets at midnight UTC.",
                headers={"X-RateLimit-Limit": str(quota), "X-RateLimit-Remaining": "0"},
            )
        return {"subscription_id": principal.subject, "tier": principal.plan, "source": "product_token"}

    key = (x_api_key or "").strip() or (api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required (X-API-Key header or api_key query)",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    from src.data.subscription_store import get_subscription_store

    store = get_subscription_store()
    sub = store.validate_api_key(key)
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Atomically reserve one request against the daily quota (no TOCTOU).
    if not store.acquire_quota(sub["id"]):
        quota = sub.get("quota_daily", 0)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily quota exceeded ({quota}/{quota}). Resets at midnight UTC.",
            headers={"X-RateLimit-Limit": str(quota), "X-RateLimit-Remaining": "0"},
        )

    return {"subscription_id": sub["id"], "tier": sub["tier"]}

# 默认财经 RSS 路由
DEFAULT_FINANCE_ROUTES = [
    "/cls/depth",          # 财联社深度
    "/cls/telegraph",      # 财联社电报
    "/wallstreetcn/live",  # 华尔街见闻快讯
]


# ================================================================ helpers
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    try:
        yield conn
    finally:
        conn.close()


def now_sh_iso() -> str:
    return datetime.now(TZ_SH).isoformat(timespec="seconds")


def ok(data, meta=None):
    return {"ok": True, "data": data, "meta": meta or {}}


def err(code: str, message: str, status: int = 400, meta=None):
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": {"code": code, "message": message},
                 "meta": meta or {}},
    )


def latest_trade_date(conn, table="bars_daily") -> str:
    row = conn.execute(f"SELECT MAX(trade_date) AS d FROM {table}").fetchone()
    return row["d"] if row else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def to_float(v):
    """None 或空串 -> None；其余转 float。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def yuan_to_yi(v):
    """元 -> 亿元（÷1e8），None 透传。"""
    f = to_float(v)
    return None if f is None else round(f / 1e8, 2)


def load_extra(row_dict, key="extra_json"):
    raw = row_dict.get(key)
    if raw:
        try:
            row_dict.update(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass
    row_dict.pop(key, None)
    return row_dict


def polarity(v) -> str:
    if v is None:
        return "neutral"
    return "positive" if v > 0 else ("negative" if v < 0 else "neutral")


# ================================================================ endpoints
@router.get("/api/v1/market/latest-trade-date")
def ep_latest_trade_date():
    with get_db() as conn:
        td = latest_trade_date(conn)
    if not td:
        return err("DATA_NOT_FOUND", "No trade date available", 404)
    return ok({"trade_date": td}, {"updated_at": now_sh_iso(), "source": "calendar"})


# ----- 2. Market Overview
@router.get("/api/v1/market/overview")
def ep_market_overview(trade_date: str = None):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn)
        if not td:
            return err("DATA_NOT_FOUND", "No trade date", 404)
        row = conn.execute("""
            SELECT total, advancers, decliners, unchanged, limit_up, limit_down,
                   turnover_billion
            FROM market_breadth_snapshot WHERE trade_date=?
        """, (td,)).fetchone()
    if not row:
        return err("DATA_NOT_FOUND", f"No breadth for trade_date={td}", 404)
    r = dict(row)
    # 构造简短 summary（基于 breadth 数值，非 AI 摘要）
    adv, dec = r["advancers"] or 0, r["decliners"] or 0
    lu = r["limit_up"] or 0
    ld = r["limit_down"] or 0
    summary = []
    if adv > dec:
        summary.append(f"上涨家数({adv})多于下跌({dec})，市场偏暖")
    elif dec > adv:
        summary.append(f"下跌家数({dec})多于上涨({adv})，市场偏弱")
    else:
        summary.append("涨跌家数接近，市场均衡")
    summary.append(f"涨停{lu}家，跌停{ld}家")
    summary.append(f"总成交额字段值 {to_float(r['turnover_billion'])}（原值，单位见 meta.note）")
    data = {
        "trade_date": td,
        "breadth": {
            "total": r["total"],
            "advancers": r["advancers"],
            "decliners": r["decliners"],
            "unchanged": r["unchanged"],
            "limit_up": r["limit_up"],
            "limit_down": r["limit_down"],
            "turnover_billion": to_float(r["turnover_billion"]),
        },
        "summary": summary,
    }
    meta = {
        "trade_date": td, "updated_at": now_sh_iso(),
        "source": "market_breadth_snapshot", "unit": "100M CNY",
        "note": "turnover_billion 为数据库原值，未经单位换算",
    }
    return ok(data, meta)


# ----- 3. Index Daily Bars
@router.get("/api/v1/indices/daily")
def ep_indices_daily(trade_date: str = None, codes: str = None):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn)
        if not td:
            return err("DATA_NOT_FOUND", "No trade date", 404)
        # 不传 codes 时返回当天全部指数（契约："all major indices"）；
        # 传了 codes 则按指定代码过滤。
        if codes:
            code_list = [c.strip() for c in codes.split(",")]
            placeholders = ",".join("?" for _ in code_list)
            rows = conn.execute(f"""
                SELECT code, trade_date, open, high, low, close, pre_close,
                       change, pct_chg, volume, total_amt
                FROM index_daily
                WHERE trade_date=? AND code IN ({placeholders})
            """, (td, *code_list)).fetchall()
        else:
            rows = conn.execute("""
                SELECT code, trade_date, open, high, low, close, pre_close,
                       change, pct_chg, volume, total_amt
                FROM index_daily
                WHERE trade_date=?
                ORDER BY code
            """, (td,)).fetchall()
        # 名称从 index_master（ZS.000001 格式）模糊匹配
        name_map = _index_name_map(conn)
    items = []
    for r in rows:
        d = dict(r)
        d["name"] = name_map.get(d["code"], _index_name_guess(d["code"]))
        for k in ("open", "high", "low", "close", "pre_close", "change",
                  "pct_chg", "volume", "total_amt"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"items": items},
              {"trade_date": td, "source": "index_daily", "unit": "100M CNY"})


def _index_name_map(conn):
    out = {}
    for r in conn.execute("SELECT code, name FROM index_master").fetchall():
        # ZS.000001 -> 000001.SH (尽力匹配后缀)
        m = re.match(r"ZS\.(\d+)", r["code"])
        if m:
            num = m.group(1)
            for suf in ("SH", "SZ", "BJ"):
                out[f"{num}.{suf}"] = r["name"]
    return out


def _index_name_guess(code):
    defaults = {"000001.SH": "上证指数", "399001.SZ": "深证成指",
                "399006.SZ": "创业板指", "000688.SH": "科创50",
                "899050.BJ": "北证50"}
    return defaults.get(code, code)


# ----- 4. Sector Fund Flow Ranking
@router.get("/api/v1/sectors/fund-flow")
def ep_sectors_fund_flow(trade_date: str = None,
                         limit: int = Query(90, ge=1, le=500),
                         order: str = "desc"):
    if order not in ("desc", "asc"):
        return err("BAD_REQUEST", "order must be desc|asc")
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "sector_capital_flow")
        if not td:
            return err("DATA_NOT_FOUND", "No sector data", 404)
        direction = "DESC" if order == "desc" else "ASC"
        rows = conn.execute(f"""
            SELECT sector, main_net, change_pct, extra_json
            FROM sector_capital_flow
            WHERE trade_date=?
            ORDER BY main_net {direction} LIMIT ?
        """, (td, limit)).fetchall()
    items = []
    for i, r in enumerate(rows, 1):
        d = {"sector": r["sector"], "main_net": to_float(r["main_net"]),
             "change_pct": to_float(r["change_pct"]),
             "extra_json": r["extra_json"]}
        d = load_extra(d)
        items.append({
            "rank": i,
            "sector": d["sector"],
            "main_net": d["main_net"],
            "change_pct": d["change_pct"],
            "leader": d.get("leader"),
            "source": d.get("source", "ths.stock_fund_flow_industry"),
        })
    return ok({"items": items},
              {"trade_date": td, "updated_at": now_sh_iso(),
               "source": "sector_capital_flow", "unit": "100M CNY"})


# ----- 5. Sector Fund Flow Intraday Curve (interpolated)
@router.get("/api/v1/sectors/fund-flow/intraday")
def ep_sectors_intraday(trade_date: str = None,
                        limit: int = Query(30, ge=1, le=200),
                        mode: str = "real_or_interpolated"):
    if mode not in ("real", "interpolated", "real_or_interpolated"):
        return err("BAD_REQUEST", "invalid mode")
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "sector_capital_flow")
        if not td:
            return err("DATA_NOT_FOUND", "No sector data", 404)
        rows = conn.execute("""
            SELECT sector, main_net, change_pct
            FROM sector_capital_flow WHERE trade_date=?
            ORDER BY ABS(main_net) DESC LIMIT ?
        """, (td, limit)).fetchall()
    # 无真实分时；用收盘 main_net 在交易日时段内线性插值
    x_axis = ["09:30", "10:30", "11:30", "14:00", "15:00"]
    frac = {"09:30": 0.0, "10:30": 0.22, "11:30": 0.45, "14:00": 0.78, "15:00": 1.0}
    items = []
    for r in rows:
        net = to_float(r["main_net"]) or 0.0
        points = [{"time": t, "main_net": round(net * frac[t], 2)} for t in x_axis]
        items.append({
            "sector": r["sector"],
            "main_net": round(net, 2),
            "change_pct": to_float(r["change_pct"]),
            "polarity": polarity(net),
            "points": points,
        })
    used_mode = "interpolated"  # 库内无真实分时
    if mode == "real":
        return ok({"mode": "real", "x_axis": x_axis, "items": []},
                  {"trade_date": td, "source": "sector_capital_flow",
                   "note": "无真实分时数据"})
    return ok({"mode": used_mode, "x_axis": x_axis, "items": items},
              {"trade_date": td, "updated_at": now_sh_iso(),
               "source": "sector_capital_flow", "unit": "100M CNY",
               "note": "mode=interpolated means visualization path, not actual intraday ticks"})


# ----- 6. Market Breadth
@router.get("/api/v1/market/breadth")
def ep_market_breadth(trade_date: str = None):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn)
        if not td:
            return err("DATA_NOT_FOUND", "No trade date", 404)
        mb = conn.execute("""
            SELECT total, advancers, decliners FROM market_breadth_snapshot
            WHERE trade_date=?
        """, (td,)).fetchone()
        # 行业板块涨跌：sector_snapshot
        ind = conn.execute("""
            SELECT
              SUM(CASE WHEN change_pct>0 THEN 1 ELSE 0 END) AS up,
              SUM(CASE WHEN change_pct<0 THEN 1 ELSE 0 END) AS down
            FROM sector_snapshot WHERE trade_date=? AND board_type='industry'
        """, (td,)).fetchone()
        # 资金流向：sector_capital_flow
        ff = conn.execute("""
            SELECT
              SUM(CASE WHEN main_net>0 THEN 1 ELSE 0 END) AS up,
              SUM(CASE WHEN main_net<0 THEN 1 ELSE 0 END) AS down
            FROM sector_capital_flow WHERE trade_date=?
        """, (td,)).fetchone()
    if not mb:
        return err("DATA_NOT_FOUND", f"No breadth for {td}", 404)
    whole_up = mb["advancers"] or 0
    whole_dn = mb["decliners"] or 0
    ind_up = ind["up"] or 0 if ind else 0
    ind_dn = ind["down"] or 0 if ind else 0
    ff_up = ff["up"] or 0 if ff else 0
    ff_dn = ff["down"] or 0 if ff else 0

    def red_ratio(u, d):
        t = u + d
        return round(u / t, 3) if t else None

    data = {
        "whole_market": {"label": "全A", "up": whole_up, "down": whole_dn,
                         "red_ratio": red_ratio(whole_up, whole_dn)},
        "industry": {"label": "行业", "up": ind_up, "down": ind_dn,
                     "red_ratio": red_ratio(ind_up, ind_dn)},
        "fund_flow": {"label": "资金", "up": ff_up, "down": ff_dn,
                      "red_ratio": red_ratio(ff_up, ff_dn)},
    }
    return ok(data, {"trade_date": td,
                     "source": "market_breadth_snapshot + sector_capital_flow"})


# ----- 7. Market Fund Summary
@router.get("/api/v1/market/fund-summary")
def ep_market_fund_summary(trade_date: str = None):
    """大盘资金汇总。数据源优先级：
    1) sector_capital_flow（板块级，当日全市场主力净额，最可靠）
    2) stock_capital_flow（个股级 m_net/r_net，可能滞后）
    3) 无任何当日数据 -> 返回全 0 占位（200 OK），meta.note 说明
    trade_date 一律回显请求值（不传则取 sector 表最新）。
    """
    def strength(v):
        if v is None:
            return 0
        return round(min(abs(v) / 800.0, 1.0), 2)  # 经验归一

    def item(label, value):
        v = value if value is not None else 0
        return {"label": label, "value": v,
                "polarity": polarity(v), "strength": strength(v)}

    with get_db() as conn:
        # 确定 trade_date：显式优先，否则取 sector_capital_flow 最新
        if not trade_date:
            trade_date = latest_trade_date(conn, "sector_capital_flow")
            if not trade_date:
                trade_date = latest_trade_date(conn, "bars_daily")
        td = trade_date

        # 主力：板块级主力净额合计（亿元，已是库单位）
        sec = conn.execute("""
            SELECT SUM(main_net) AS main_net FROM sector_capital_flow
            WHERE trade_date=?
        """, (td,)).fetchone()
        # 散户/小单：个股级 r_net（元，需 ÷1e8）
        stk = conn.execute("""
            SELECT SUM(m_net) AS m_net, SUM(r_net) AS r_net
            FROM stock_capital_flow WHERE trade_date=?
        """, (td,)).fetchone()

    sec_main = to_float(sec["main_net"]) if sec else None       # 板块主力(亿元)
    stk_main = yuan_to_yi(stk["m_net"]) if stk else None        # 个股主力(亿元)
    stk_retail = yuan_to_yi(stk["r_net"]) if stk else None      # 个股散户(亿元)

    notes = []
    has_any = sec_main is not None or stk_main is not None or stk_retail is not None

    if not has_any:
        # 当日无任何资金数据 -> 全 0 占位
        items = [item(l, 0) for l in ("大单", "中单", "小单", "主力")]
        return ok({"items": items},
                  {"trade_date": td, "unit": "100M CNY",
                   "source": "none",
                   "note": f"{td} 暂无资金流数据，各项按 0 占位"})

    # 主力口径：优先板块级（更全更准），否则用个股级
    if sec_main is not None:
        zhu = sec_main
        notes.append("主力=板块级资金流合计(SUM main_net)")
    else:
        zhu = stk_main or 0.0
        notes.append("主力=个股级资金流合计(无板块数据)")

    # 小单口径：个股散户净额；无则 0
    if stk_retail is not None:
        xiao = stk_retail
        notes.append("小单=个股散户净额(SUM r_net)")
    else:
        xiao = 0.0
        notes.append("小单=0(个股资金流当日无数据)")

    # 大单 ≈ 主力的主体部分；中单由零和反推（主力+中单+小单=0）
    big = round(zhu * 0.7, 2)
    mid = round(-(zhu + xiao), 2)
    notes.append("大/中单为可解释派生值(大单=主力×0.7，中单=零和反推)，非真实分单")

    items = [
        item("大单", big),
        item("中单", mid),
        item("小单", xiao),
        item("主力", round(zhu, 2)),
    ]
    return ok({"items": items},
              {"trade_date": td, "unit": "100M CNY",
               "source": "sector_capital_flow + stock_capital_flow",
               "note": " | ".join(notes)})


# ----- 8. Hot Stock Pool
@router.get("/api/v1/stocks/hot-pool")
def ep_hot_pool(trade_date: str = None,
                pool_type: str = "limitup",
                limit: int = Query(30, ge=1, le=500)):
    valid = {"limitup", "limitdown", "strong", "fire", "previous", "secnew"}
    if pool_type not in valid:
        return err("BAD_REQUEST", f"pool_type must be one of {sorted(valid)}")
    with get_db() as conn:
        td = trade_date or conn.execute(
            "SELECT MAX(trade_date) AS d FROM stock_pool WHERE pool_type=?",
            (pool_type,)).fetchone()["d"]
        if not td:
            return err("DATA_NOT_FOUND", f"No {pool_type} data", 404)
        rows = conn.execute("""
            SELECT code, extra_json FROM stock_pool
            WHERE pool_type=? AND trade_date=?
        """, (pool_type, td)).fetchall()
    enriched = []
    for r in rows:
        enriched.append(load_extra(dict(r)))
    # 先排全量，再 limit —— 否则 limit=10 会把高连板挡在外面
    #   limitup/strong 按连板数降序；其它按代码兜底
    if pool_type in ("limitup", "strong"):
        enriched.sort(key=lambda x: (to_float(x.get("c_times")) or 0,
                                     to_float(x.get("rise_rate")) or 0), reverse=True)
    enriched = enriched[:limit]
    items = []
    for i, d in enumerate(enriched, 1):
        items.append({
            "rank": i,
            "code": d.get("code"),
            "name": d.get("name"),
            "industry": d.get("industry"),
            "rise_rate": to_float(d.get("rise_rate")),
            "continuous_limit": d.get("c_times"),
            "theme": d.get("theme"),
            "extra": {k: v for k, v in d.items()
                      if k not in ("code", "name", "industry", "rise_rate",
                                   "c_times", "theme")},
        })
    return ok({"pool_type": pool_type, "items": items},
              {"trade_date": td, "source": "stock_pool"})


# ----- 9. Stock Metadata
@router.get("/api/v1/stocks/metadata")
def ep_stock_metadata(codes: str = Query(..., description="comma-separated codes")):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return err("BAD_REQUEST", "codes required")
    with get_db() as conn:
        placeholders = ",".join("?" for _ in code_list)
        rows = conn.execute(f"""
            SELECT code, name, industry, market FROM security_master
            WHERE code IN ({placeholders})
        """, code_list).fetchall()
    return ok({"items": rows_to_dicts(rows)}, {"source": "security_master"})


# ----- 10. Stock Daily Bars (history)
@router.get("/api/v1/stocks/daily")
def ep_stocks_daily(code: str = Query(..., description="stock code, e.g. 000001"),
                    start: str = None, end: str = None,
                    limit: int = Query(250, ge=1, le=2000)):
    code = code.strip()
    sql = "SELECT code, name, trade_date, open, high, low, close, volume, total_amt, rise_rate, t_rate, source FROM bars_daily WHERE code=?"
    params: list = [code]
    if start:
        sql += " AND trade_date>=?"
        params.append(start)
    if end:
        sql += " AND trade_date<=?"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No bars for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("open", "high", "low", "close", "volume", "total_amt", "rise_rate", "t_rate"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "count": len(items), "items": items},
              {"source": "bars_daily", "order": "trade_date desc"})


# ----- 10b. Stock Daily Basic (valuation)
@router.get("/api/v1/stocks/daily-basic")
def ep_stocks_daily_basic(trade_date: str = None,
                          codes: str = Query(None, description="comma-separated codes, max 50"),
                          limit: int = Query(100, ge=1, le=500)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "stock_daily_basic")
        if not td:
            return err("DATA_NOT_FOUND", "No daily_basic data", 404)
        sql = """SELECT b.code, s.name, b.close, b.turnover_rate, b.volume_ratio,
                        b.pe, b.pe_ttm, b.pb, b.ps, b.ps_ttm, b.dv_ratio, b.dv_ttm,
                        b.total_share, b.float_share, b.total_mv, b.circ_mv
                 FROM stock_daily_basic b LEFT JOIN security_master s ON s.code=b.code
                 WHERE b.trade_date=?"""
        params: list = [td]
        if codes:
            code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
            if code_list:
                sql += f" AND b.code IN ({','.join('?' for _ in code_list)})"
                params.extend(code_list)
        sql += " ORDER BY b.total_mv DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("close", "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb",
                  "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_share", "float_share",
                  "total_mv", "circ_mv"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "stock_daily_basic", "mv_unit": "10000 CNY (万元)"})


# ----- 10c. ETF / Fund daily bars
@router.get("/api/v1/etf/daily")
def ep_etf_daily(code: str = Query(...), start: str = None, end: str = None,
                 limit: int = Query(250, ge=1, le=2000)):
    return _fund_like_daily("etf_daily", code, start, end, limit)


@router.get("/api/v1/fund/daily")
def ep_fund_daily(code: str = Query(...), start: str = None, end: str = None,
                  limit: int = Query(250, ge=1, le=2000)):
    return _fund_like_daily("fund_daily", code, start, end, limit)


def _fund_like_daily(table: str, code: str, start: str, end: str, limit: int):
    code = code.strip()
    # fund_daily has rise_rate + nav/iopv; etf_daily only has rise.
    extra_cols = ", rise_rate, nav, iopv" if table == "fund_daily" else ""
    sql = f"""SELECT code, trade_date, open, high, low, close, volume, total_amt, rise{extra_cols}
              FROM {table} WHERE code=?"""
    params: list = [code]
    if start:
        sql += " AND trade_date>=?"
        params.append(start)
    if end:
        sql += " AND trade_date<=?"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No bars for code={code} in {table}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in list(d.keys()):
            if k not in ("code", "trade_date"):
                d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "count": len(items), "items": items},
              {"source": table, "order": "trade_date desc"})


# ----- 10d. Board (industry/concept) daily bars & members
@router.get("/api/v1/boards/daily")
def ep_boards_daily(board_code: str = None, trade_date: str = None,
                    board_type: str = None, start: str = None, end: str = None,
                    limit: int = Query(100, ge=1, le=2000)):
    # No board_code: list all boards for the (given or latest) date.
    sql = "SELECT board_code, name, board_type, trade_date, open, high, low, close, volume, total_amt, rise, rise_rate, turnover_rate FROM board_daily WHERE 1=1"
    params: list = []
    if board_code:
        sql += " AND board_code=?"
        params.append(board_code.strip())
    else:
        if not trade_date:
            with get_db() as conn:
                trade_date = latest_trade_date(conn, "board_daily")
        sql += " AND trade_date=?"
        params.append(trade_date)
        if board_type:
            sql += " AND board_type=?"
            params.append(board_type)
    if board_code:
        if start:
            sql += " AND trade_date>=?"
            params.append(start)
        if end:
            sql += " AND trade_date<=?"
            params.append(end)
        sql += " ORDER BY trade_date DESC LIMIT ?"
    else:
        sql += " ORDER BY rise_rate DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", "No board data", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("open", "high", "low", "close", "volume", "total_amt", "rise", "rise_rate", "turnover_rate"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"count": len(items), "items": items},
              {"source": "board_daily", "order": "trade_date desc" if board_code else "rise_rate desc"})


@router.get("/api/v1/boards/members")
def ep_boards_members(board_code: str = Query(..., description="board code"),
                      limit: int = Query(200, ge=1, le=2000)):
    board_code = board_code.strip()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT board_code, board_type, stock_code, stock_name, stock_exchange
            FROM board_members WHERE board_code=? LIMIT ?
        """, (board_code, limit)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No members for board_code={board_code}", 404)
    return ok({"board_code": board_code, "count": len(rows), "items": rows_to_dicts(rows)},
              {"source": "board_members"})


# ----- 10e. Realtime quote snapshot (5-min granularity)
@router.get("/api/v1/quotes/realtime")
def ep_quotes_realtime(codes: str = Query(..., description="comma-separated codes, max 50")):
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
    if not code_list:
        return err("BAD_REQUEST", "codes required")
    with get_db() as conn:
        td = latest_trade_date(conn, "realtime_quote_snapshot")
        if not td:
            return err("DATA_NOT_FOUND", "No realtime snapshot", 404)
        placeholders = ",".join("?" for _ in code_list)
        rows = conn.execute(f"""
            SELECT code, name, snapshot_at, price, pre_close, open, high, low,
                   volume, total_amt, rise, rise_rate, turnover_rate, source
            FROM realtime_quote_snapshot
            WHERE trade_date=? AND code IN ({placeholders})
        """, [td, *code_list]).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("price", "pre_close", "open", "high", "low", "volume", "total_amt", "rise", "rise_rate", "turnover_rate"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "realtime_quote_snapshot", "note": "5-minute snapshot granularity"})


# ----- 10f. Fund-flow / capital-flow endpoints (A2)
@router.get("/api/v1/stocks/fund-flow")
def ep_stocks_fund_flow(code: str = Query(...), start: str = None, end: str = None,
                        limit: int = Query(120, ge=1, le=2000)):
    """Per-stock daily fund flow (main/super/large/mid/small net, sina source)."""
    code = code.strip()
    sql = """SELECT code, trade_date, main_net, super_net, large_net, mid_net, small_net,
                    net_amount, turnover FROM fund_flow_daily WHERE code=?"""
    params: list = [code]
    if start:
        sql += " AND trade_date>=?"
        params.append(start)
    if end:
        sql += " AND trade_date<=?"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No fund-flow for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("main_net", "super_net", "large_net", "mid_net", "small_net", "net_amount", "turnover"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "count": len(items), "items": items},
              {"source": "fund_flow_daily", "order": "trade_date desc"})


@router.get("/api/v1/stocks/capital-flow")
def ep_stocks_capital_flow(trade_date: str = None,
                           codes: str = Query(..., description="comma-separated codes, max 50"),
                           period: int = None):
    """Per-stock capital flow snapshots (period dimension, tushare-style)."""
    if period is not None and period not in (1, 3, 5, 10):
        return err("BAD_REQUEST", "period must be one of [1, 3, 5, 10]")
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
    if not code_list:
        return err("BAD_REQUEST", "codes required")
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "stock_capital_flow")
        if not td:
            return err("DATA_NOT_FOUND", "No capital-flow data", 404)
        sql = """SELECT code, trade_date, period, m_in, m_out, m_net, r_in, r_out, r_net
                 FROM stock_capital_flow WHERE trade_date=? AND code IN
                 ({placeholders})""".format(placeholders=",".join("?" for _ in code_list))
        params: list = [td, *code_list]
        if period is not None:
            sql += " AND period=?"
            params.append(period)
        sql += " ORDER BY code, period"
        rows = conn.execute(sql, params).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("m_in", "m_out", "m_net", "r_in", "r_out", "r_net"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "stock_capital_flow", "unit": "100M CNY (亿元)"})


@router.get("/api/v1/stocks/capital-rank")
def ep_stocks_capital_rank(trade_date: str = None,
                           rank_type: str = "inflow",
                           order: str = "desc",
                           limit: int = Query(50, ge=1, le=500)):
    if rank_type not in ("inflow", "outflow"):
        return err("BAD_REQUEST", "rank_type must be one of ['inflow', 'outflow']")
    if order not in ("asc", "desc"):
        return err("BAD_REQUEST", "order must be 'asc' or 'desc'")
    with get_db() as conn:
        td = trade_date or conn.execute(
            "SELECT MAX(trade_date) AS d FROM stock_capital_rank WHERE rank_type=?",
            (rank_type,)).fetchone()["d"]
        if not td:
            return err("DATA_NOT_FOUND", f"No {rank_type} rank data", 404)
        direction = "DESC" if order == "desc" else "ASC"
        rows = conn.execute(f"""
            SELECT code, name, main_net, change_pct, extra_json
            FROM stock_capital_rank
            WHERE trade_date=? AND rank_type=?
            ORDER BY main_net {direction} LIMIT ?
        """, (td, rank_type, limit)).fetchall()
    items = []
    for i, r in enumerate(rows, 1):
        d = load_extra(dict(r))
        d["rank"] = i
        d["main_net"] = to_float(d.get("main_net"))
        d["change_pct"] = to_float(d.get("change_pct"))
        items.append(d)
    return ok({"trade_date": td, "rank_type": rank_type, "items": items},
              {"source": "stock_capital_rank", "unit": "100M CNY (亿元)"})


@router.get("/api/v1/northbound/flow")
def ep_northbound_flow(trade_date: str = None):
    """Northbound net-buy intraday series (minute granularity, unit 亿元)."""
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "northbound_flow")
        if not td:
            return err("DATA_NOT_FOUND", "No northbound data", 404)
        rows = conn.execute("""
            SELECT time, hgt_yi, sgt_yi FROM northbound_flow
            WHERE trade_date=? ORDER BY time
        """, (td,)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No northbound rows for {td}", 404)
    items = [{"time": r["time"], "hgt_yi": to_float(r["hgt_yi"]), "sgt_yi": to_float(r["sgt_yi"])}
             for r in rows]
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "northbound_flow", "unit": "100M CNY (亿元)", "note": "minute granularity"})


# ----- 10g. Limit pools / dragon-tiger / hot list / regime (A3)
_LIMIT_POOL_TABLES = {
    "zt": ("zt_pool", "limit_days"),
    "dt": ("dt_pool", "dt_days"),
    "zb": ("zb_pool", "break_times"),
    "yzt": ("yzt_pool", "y_limit_days"),
}


@router.get("/api/v1/stocks/limit-pool")
def ep_stocks_limit_pool(pool_type: str = "zt",
                         trade_date: str = None,
                         limit: int = Query(100, ge=1, le=500)):
    """Detailed limit-up/down/broken/yesterday-limit pools (eastmoney source)."""
    if pool_type not in _LIMIT_POOL_TABLES:
        return err("BAD_REQUEST", f"pool_type must be one of {sorted(_LIMIT_POOL_TABLES)}")
    table, order_col = _LIMIT_POOL_TABLES[pool_type]
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, table)
        if not td:
            return err("DATA_NOT_FOUND", f"No {pool_type} pool data", 404)
        rows = conn.execute(f"""
            SELECT * FROM {table} WHERE trade_date=?
            ORDER BY {order_col} DESC LIMIT ?
        """, (td, limit)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No {pool_type} pool rows for {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        d.pop("updated_at", None)
        for k in list(d.keys()):
            if k in ("code", "name", "industry", "zt_stat", "first_seal", "last_seal",
                     "y_first_seal", "source", "trade_date"):
                continue
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "pool_type": pool_type, "count": len(items), "items": items},
              {"source": table})


@router.get("/api/v1/dragon-tiger")
def ep_dragon_tiger(trade_date: str = None, code: str = None,
                    limit: int = Query(100, ge=1, le=500)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "dragon_tiger")
        if not td:
            return err("DATA_NOT_FOUND", "No dragon-tiger data", 404)
        sql = """SELECT code, trade_date, name, close, rise_rate, net_amt, buy_amt,
                        sell_amt, extra_json FROM dragon_tiger WHERE trade_date=?"""
        params: list = [td]
        if code:
            sql += " AND code=?"
            params.append(code.strip())
        sql += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No dragon-tiger rows for {td}", 404)
    items = []
    for r in rows:
        d = load_extra(dict(r))
        for k in ("close", "rise_rate", "net_amt", "buy_amt", "sell_amt"):
            d[k] = to_float(d.get(k))
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "dragon_tiger", "unit": "100M CNY (亿元)"})


@router.get("/api/v1/hot-list")
def ep_hot_list(trade_date: str = None, source: str = None,
                limit: int = Query(50, ge=1, le=200)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "hot_list")
        if not td:
            return err("DATA_NOT_FOUND", "No hot-list data", 404)
        sql = """SELECT code, name, rank, hot_value, change_pct, tags, source
                 FROM hot_list WHERE trade_date=?"""
        params: list = [td]
        if source:
            sql += " AND source=?"
            params.append(source)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No hot-list rows for {td}", 404)
    items = [{"code": r["code"], "name": r["name"], "rank": r["rank"],
              "hot_value": to_float(r["hot_value"]), "change_pct": to_float(r["change_pct"]),
              "tags": r["tags"], "source": r["source"]} for r in rows]
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "hot_list"})


@router.get("/api/v1/market/regime")
def ep_market_regime(trade_date: str = None):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "market_regime")
        if not td:
            return err("DATA_NOT_FOUND", "No regime data", 404)
        row = conn.execute("""
            SELECT trade_date, regime, confidence, bull_score, bear_score,
                   strong_trend, indicators_json
            FROM market_regime WHERE trade_date=?
        """, (td,)).fetchone()
    if not row:
        return err("DATA_NOT_FOUND", f"No regime for {td}", 404)
    d = dict(row)
    indicators = None
    if d.get("indicators_json"):
        try:
            indicators = json.loads(d["indicators_json"])
        except (json.JSONDecodeError, TypeError):
            indicators = None
    data = {
        "trade_date": d["trade_date"], "regime": d["regime"],
        "confidence": to_float(d["confidence"]),
        "bull_score": to_float(d["bull_score"]), "bear_score": to_float(d["bear_score"]),
        "strong_trend": d["strong_trend"], "indicators": indicators,
    }
    return ok(data, {"source": "market_regime"})


# ----- 10h. Fundamentals endpoints (A4)
@router.get("/api/v1/stocks/financial-snapshot")
def ep_financial_snapshot(codes: str = Query(..., description="comma-separated codes, max 50")):
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
    if not code_list:
        return err("BAD_REQUEST", "codes required")
    with get_db() as conn:
        placeholders = ",".join("?" for _ in code_list)
        rows = conn.execute(f"""
            SELECT code, trade_date, liutongguben, zongguben, eps, bvps, roe,
                   profit, income, extra_json
            FROM financial_snapshot WHERE code IN ({placeholders})
        """, code_list).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", "No financial snapshots", 404)
    items = []
    for r in rows:
        d = load_extra(dict(r))
        for k in ("liutongguben", "zongguben", "eps", "bvps", "roe", "profit", "income"):
            d[k] = to_float(d.get(k))
        items.append(d)
    return ok({"count": len(items), "items": items}, {"source": "financial_snapshot"})


@router.get("/api/v1/stocks/financial-statement")
def ep_financial_statement(code: str = Query(...), report_type: str = None,
                           limit: int = Query(8, ge=1, le=20)):
    """Financial statements (three reports). report_type: lrb/zcfzb/xjlb."""
    if report_type is not None and report_type not in ("lrb", "zcfzb", "xjlb"):
        return err("BAD_REQUEST", "report_type must be one of ['lrb', 'zcfzb', 'xjlb']")
    code = code.strip()
    sql = """SELECT code, report_date, report_type, payload_json
             FROM financial_statement WHERE code=?"""
    params: list = [code]
    if report_type:
        sql += " AND report_type=?"
        params.append(report_type)
    sql += " ORDER BY report_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No statements for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.pop("payload_json"))
        except (json.JSONDecodeError, TypeError):
            d["payload"] = None
        items.append(d)
    return ok({"code": code, "count": len(items), "items": items},
              {"source": "financial_statement"})


@router.get("/api/v1/stocks/eps-forecast")
def ep_eps_forecast(code: str = Query(...), year: str = None):
    code = code.strip()
    sql = """SELECT code, trade_date, year, count, min_eps, mean_eps, max_eps, net_profit
             FROM eps_forecast WHERE code=?"""
    params: list = [code]
    if year:
        sql += " AND year=?"
        params.append(year)
    sql += " ORDER BY trade_date DESC, year"
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No EPS forecast for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("min_eps", "mean_eps", "max_eps", "net_profit"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "items": items}, {"source": "eps_forecast"})


@router.get("/api/v1/stocks/margin")
def ep_stocks_margin(trade_date: str = None, code: str = None,
                     limit: int = Query(100, ge=1, le=500)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "margin_trading")
        if not td:
            return err("DATA_NOT_FOUND", "No margin data", 404)
        sql = """SELECT code, trade_date, rzye, rzmre, rzche, rqye, rqmcl, rqchl, rzrqye
                 FROM margin_trading WHERE trade_date=?"""
        params: list = [td]
        if code:
            sql += " AND code=?"
            params.append(code.strip())
        sql += " ORDER BY rzrqye DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No margin rows for {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("rzye", "rzmre", "rzche", "rqye", "rqmcl", "rqchl", "rzrqye"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "margin_trading", "unit": "CNY (元)"})


@router.get("/api/v1/stocks/block-trade")
def ep_block_trade(trade_date: str = None, code: str = None,
                   limit: int = Query(100, ge=1, le=500)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "block_trade")
        if not td:
            return err("DATA_NOT_FOUND", "No block-trade data", 404)
        sql = """SELECT code, trade_date, price, close, premium_pct, vol, amount,
                        buyer, seller FROM block_trade WHERE trade_date=?"""
        params: list = [td]
        if code:
            sql += " AND code=?"
            params.append(code.strip())
        sql += " ORDER BY amount DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No block-trade rows for {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("price", "close", "premium_pct", "vol", "amount"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "block_trade"})


@router.get("/api/v1/stocks/holder-num")
def ep_holder_num(code: str = Query(...), start: str = None, end: str = None,
                  limit: int = Query(20, ge=1, le=100)):
    code = code.strip()
    sql = """SELECT code, end_date, holder_num, change_num, change_ratio, avg_shares
             FROM holder_num WHERE code=?"""
    params: list = [code]
    if start:
        sql += " AND end_date>=?"
        params.append(start)
    if end:
        sql += " AND end_date<=?"
        params.append(end)
    sql += " ORDER BY end_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No holder-num for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("holder_num", "change_num", "change_ratio", "avg_shares"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "items": items}, {"source": "holder_num"})


@router.get("/api/v1/stocks/dividends")
def ep_dividends(code: str = Query(...)):
    code = code.strip()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT code, ex_date, bonus_rmb, transfer_ratio, bonus_ratio, plan
            FROM dividend_history WHERE code=? ORDER BY ex_date DESC
        """, (code,)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No dividends for code={code}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("bonus_rmb", "transfer_ratio", "bonus_ratio"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "items": items}, {"source": "dividend_history"})


# ----- 10i. Fund/ETF premium & market stats (A5/A6)
@router.get("/api/v1/funds/premium")
def ep_funds_premium(trade_date: str = None, type: str = None,
                     limit: int = Query(50, ge=1, le=200)):
    """LOF/ETF premium/discount snapshot, sorted by |premium_rate| desc."""
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "fund_premium_snapshot")
        if not td:
            return err("DATA_NOT_FOUND", "No premium data", 404)
        sql = """SELECT code, name, type, price, nav, premium_rate, amount,
                        change_pct, redeem_status, subscribe_status, signal, iopv, nav_date
                 FROM fund_premium_snapshot WHERE trade_date=?"""
        params: list = [td]
        if type:
            sql += " AND type=?"
            params.append(type)
        sql += " ORDER BY ABS(premium_rate) DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No premium rows for {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("price", "nav", "premium_rate", "amount", "change_pct", "iopv"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "fund_premium_snapshot", "order": "|premium_rate| desc"})


@router.get("/api/v1/funds/arbitrage-signals")
def ep_arbitrage_signals(status: str = "ACTIVE",
                         limit: int = Query(50, ge=1, le=200)):
    if status not in ("ACTIVE", "EXPIRED", "EXECUTED"):
        return err("BAD_REQUEST", "status must be one of ['ACTIVE', 'EXPIRED', 'EXECUTED']")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT code, trade_date, name, type, signal_type, premium_rate, z_score,
                   historical_mean, historical_std, n_history, cost_estimate, net_spread, status
            FROM arbitrage_signal WHERE status=?
            ORDER BY ABS(z_score) DESC LIMIT ?
        """, (status, limit)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No {status} signals", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("premium_rate", "z_score", "historical_mean", "historical_std",
                  "cost_estimate", "net_spread"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"status": status, "count": len(items), "items": items},
              {"source": "arbitrage_signal"})


@router.get("/api/v1/etf/share-size")
def ep_etf_share_size(trade_date: str = None,
                      limit: int = Query(100, ge=1, le=500)):
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "etf_share_size")
        if not td:
            return err("DATA_NOT_FOUND", "No share-size data", 404)
        rows = conn.execute("""
            SELECT code, name, total_share, total_size, nav, close, exchange
            FROM etf_share_size WHERE trade_date=?
            ORDER BY total_size DESC LIMIT ?
        """, (td, limit)).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No share-size rows for {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("total_share", "total_size", "nav", "close"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"trade_date": td, "count": len(items), "items": items},
              {"source": "etf_share_size"})


@router.get("/api/v1/option-chain")
def ep_option_chain(underlying: str = "510050", trade_date: str = None,
                    call_put: str = None,
                    limit: int = Query(200, ge=1, le=1000)):
    if call_put is not None and call_put not in ("C", "P", "call", "put"):
        return err("BAD_REQUEST", "call_put must be one of ['C', 'P']")
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "option_chain")
        if not td:
            return err("DATA_NOT_FOUND", "No option data", 404)
        sql = """SELECT code, underlying, month, call_put, bid, ask, last, strike,
                        open_interest, volume, delta, gamma, theta, vega, iv
                 FROM option_chain WHERE underlying=? AND trade_date=?"""
        params: list = [underlying.strip(), td]
        if call_put:
            params.append(call_put[0].upper())
            sql += " AND call_put=?"
        sql += " ORDER BY strike LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No option rows for {underlying} @ {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("bid", "ask", "last", "strike", "open_interest", "volume",
                  "delta", "gamma", "theta", "vega", "iv"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"underlying": underlying, "trade_date": td, "count": len(items), "items": items},
              {"source": "option_chain"})


@router.get("/api/v1/market/stage-snapshot")
def ep_stage_snapshot(trade_date: str = None, stage: str = None):
    """Per-stage market snapshots (premarket/intraday/...). stage optional."""
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "market_stage_snapshot")
        if not td:
            return err("DATA_NOT_FOUND", "No stage snapshot data", 404)
        sql = "SELECT stage, payload_json, source_tables, updated_at FROM market_stage_snapshot WHERE trade_date=?"
        params: list = [td]
        if stage:
            sql += " AND stage=?"
            params.append(stage)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No stage snapshot for {td}", 404)
    items = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = None
        items.append({"stage": r["stage"], "payload": payload,
                      "source_tables": r["source_tables"]})
    return ok({"trade_date": td, "items": items}, {"source": "market_stage_snapshot"})


# ----- 10j. fq-factors + minute bars + wolf passthrough (B1-B3)
@router.get("/api/v1/stocks/fq-factors")
def ep_fq_factors(code: str = Query(...), start: str = None, end: str = None,
                  limit: int = Query(250, ge=1, le=2000)):
    code = code.strip()
    sql = "SELECT code, trade_date, adj_factor, source FROM fq_factors WHERE code=?"
    params: list = [code]
    if start:
        sql += " AND trade_date>=?"
        params.append(start)
    if end:
        sql += " AND trade_date<=?"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No fq factors for code={code}", 404)
    items = [{"code": r["code"], "trade_date": r["trade_date"],
              "adj_factor": to_float(r["adj_factor"]), "source": r["source"]} for r in rows]
    return ok({"code": code, "count": len(items), "items": items},
              {"source": "fq_factors", "order": "trade_date desc"})


_MINUTE_BUCKET = {"5m": 1, "15m": 3, "30m": 6, "60m": 12}


@router.get("/api/v1/stocks/minute")
def ep_stocks_minute(code: str = Query(...), trade_date: str = None,
                     start: str = None, end: str = None,
                     period: str = "5m"):
    """5m bars from the hot-pool universe; 15m/30m/60m aggregated in SQL."""
    if period not in _MINUTE_BUCKET:
        return err("BAD_REQUEST", f"period must be one of {sorted(_MINUTE_BUCKET)}")
    code = code.strip()
    with get_db() as conn:
        td = trade_date or latest_trade_date(conn, "minute_bars")
        if not td:
            return err("DATA_NOT_FOUND", "No minute bars yet (hot-pool sync starts tonight)", 404)
        bucket = _MINUTE_BUCKET[period]
        if bucket == 1:
            sql = """SELECT code, trade_date, bar_time, open, high, low, close, volume, total_amt
                     FROM minute_bars WHERE code=? AND trade_date=? ORDER BY bar_time"""
            params: list = [code, td]
        else:
            # Aggregate 5m bars into the requested bucket. Bucket index =
            # position of the bar in the session (09:35 is bar 1); bars beyond
            # 11:30/13:00 lunch boundary are offset so afternoon maps after
            # morning in a monotonic sequence.
            sql = """
                WITH seq AS (
                    SELECT bar_time, open, high, low, close, volume, total_amt,
                           (CAST(substr(bar_time, 1, 2) AS INTEGER) * 60
                            + CAST(substr(bar_time, 4, 2) AS INTEGER)) AS tmin
                    FROM minute_bars WHERE code=? AND trade_date=?
                ),
                bucketed AS (
                    SELECT *,
                           (ROW_NUMBER() OVER (ORDER BY tmin) - 1) / :bucket AS bidx
                    FROM seq
                )
                SELECT ? AS code, ? AS trade_date,
                       MAX(bar_time) AS bar_time,
                       (SELECT open FROM bucketed b2 WHERE b2.bidx = b1.bidx
                         ORDER BY tmin LIMIT 1) AS open,
                       MAX(high) AS high, MIN(low) AS low,
                       (SELECT close FROM bucketed b3 WHERE b3.bidx = b1.bidx
                         ORDER BY tmin DESC LIMIT 1) AS close,
                       SUM(volume) AS volume, SUM(total_amt) AS total_amt
                FROM bucketed b1 GROUP BY bidx ORDER BY bidx
            """
            params = [code, td, code, td]
            # sqlite3 named param mixed with positional is messy — inline bucket.
            sql = sql.replace(":bucket", str(bucket))
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return err("DATA_NOT_FOUND", f"No minute bars for code={code} @ {td}", 404)
    items = []
    for r in rows:
        d = dict(r)
        for k in ("open", "high", "low", "close", "volume", "total_amt"):
            d[k] = to_float(d[k])
        items.append(d)
    return ok({"code": code, "trade_date": td, "period": period,
               "count": len(items), "items": items},
              {"source": "minute_bars", "unit_note": "volume 手 / amount 元",
               "coverage": "hot-pool universe only"})


def _wolf_passthrough(path: str, **params):
    """Shared wolf passthrough wrapper: 502 with a clear error when upstream is
    unavailable (token missing / network), rows capped at ROWS_HARD_CAP."""
    from src.data import wolf_client
    from src.data.wolf_client import WolfError, WolfNotConfiguredError

    try:
        rows = wolf_client.call(path, **params)
    except WolfNotConfiguredError as exc:
        return err("UPSTREAM_UNAVAILABLE", str(exc), 502)
    except (WolfError, Exception) as exc:  # noqa: BLE001
        return err("UPSTREAM_UNAVAILABLE", f"wolf upstream failed: {exc}", 502)
    truncated = len(rows) > ROWS_HARD_CAP
    return ok({"count": min(len(rows), ROWS_HARD_CAP), "items": rows[:ROWS_HARD_CAP]},
              {"passthrough": "wolf", "cached": False,
               "truncated": truncated, "upstream": path})


@router.get("/api/v1/stocks/ticks")
def ep_stocks_ticks(code: str = Query(...), trade_date: str = None):
    """Per-tick trades for one code (wolf /wolf/deal passthrough, not stored)."""
    return _wolf_passthrough("wolf/deal", code=code.strip(), tradeDate=trade_date)


@router.get("/api/v1/stocks/quote5")
def ep_stocks_quote5(code: str = Query(...)):
    """Level-5 order book for one code (wolf /wolf/time/five passthrough)."""
    return _wolf_passthrough("wolf/time/five", symbol="stock", code=code.strip())


# ----- 11. Finance RSS Summary (含聚类)
@router.get("/api/v1/news/finance/rss-summary")
def ep_news_rss_summary(routes: str = None,
                        limit: int = Query(50, ge=1, le=200),
                        since: str = None):
    route_list = [r.strip() for r in routes.split(",")] if routes else DEFAULT_FINANCE_ROUTES
    items = []
    for route in route_list:
        items.extend(_fetch_rss_items(route, limit=limit))
    # 去重（按 link）
    seen = set()
    dedup = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)
    # since 过滤
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            dedup = [i for i in dedup
                     if i.get("published_at_dt")
                     and i["published_at_dt"] >= since_dt]
        except ValueError:
            pass
    dedup = dedup[:limit]
    # 清掉内部字段
    for i in dedup:
        i.pop("published_at_dt", None)
    return ok({"items": dedup, "clusters": []},
              {"updated_at": now_sh_iso(), "source": "local_rsshub"})


def _fetch_rss_items(route, limit):
    url = f"{RSSHUB_URL}{route}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sigmx-query/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []  # 单个路由失败不影响其它
    return _parse_rss_xml(raw, route)[:limit]


def _parse_rss_xml(xml_text, route):
    items = []
    # 轻量正则解析 item（RSSHub 默认 RSS 2.0 / atom 兼容）
    for m in re.finditer(r"<item>(.*?)</item>", xml_text, re.S):
        block = m.group(1)

        def pick(tag):
            mm = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _strip_cdata(mm.group(1)).strip() if mm else None
        title = pick("title")
        link = pick("link") or pick("guid")
        desc = pick("description")
        pub = pick("pubDate")
        source = _route_source_name(route)
        summary = _html_to_text(desc)[:300] if desc else None
        pub_dt = _parse_pubdate(pub)
        items.append({
            "route": route,
            "source": source,
            "title": title,
            "summary": summary,
            "link": link,
            "published_at": pub_dt.isoformat(timespec="seconds") if pub_dt else None,
            "published_at_dt": pub_dt,
        })
    return items


def _strip_cdata(s):
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)


def _html_to_text(s):
    import html
    s = html.unescape(s)            # 反转义 &lt; &gt; &quot; &amp; 等
    s = re.sub(r"<[^>]+>", " ", s)  # 去标签
    s = html.unescape(s)            # 处理反转义后可能出现的二次转义
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _route_source_name(route):
    if "cls" in route:
        return "财联社"
    if "wallstreetcn" in route:
        return "华尔街见闻"
    if "caixin" in route:
        return "财新"
    return route


def _parse_pubdate(s):
    if not s:
        return None
    s = s.strip()
    # strptime %z 不认 GMT/UTC，统一替换为 +0000
    s = re.sub(r"\bGMT\b", "+0000", s)
    s = re.sub(r"\bUTC\b", "+0000", s)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(TZ_SH)
        except ValueError:
            continue
    return None


# ================================================================ misc


# ----- 11. Morning Briefing Triptych (早盘内参三图)
# 文档: GET /api/v1/content/morning-briefing-triptych
# 聚合 global_market_index_daily + us_a_share_transmission + premarket_news
@router.get("/api/v1/content/morning-briefing-triptych")
def ep_morning_briefing(trade_date: str = None,
                        mode: str = "render",
                        limit: int = Query(5, ge=1, le=10)):
    # 日期校验
    if trade_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", trade_date):
            return JSONResponse(status_code=400, content={
                "ok": False, "error": {"code": "INVALID_DATE",
                "message": "trade_date must be YYYY-MM-DD"}})

    with get_db() as conn:
        # 确定 trade_date：取三表都有数据的最新公共日期（各表最新日期的最小值）。
        # 海外表常比 A 股表早一天（隔夜美股先出），取最大值会导致 premarket_news 缺失 -> partial。
        if not trade_date:
            dates = []
            for t in ("global_market_index_daily", "us_a_share_transmission",
                      "premarket_news"):
                d = latest_trade_date(conn, t)
                if d:
                    dates.append(d)
            if dates:
                trade_date = min(dates)
        td = trade_date
        if not td:
            return JSONResponse(status_code=404, content={
                "ok": False, "error": {"code": "NO_DATA",
                "message": "No morning briefing data"}})

        # Fallback to latest available date if requested date has no data
        # (e.g., requesting 2026-07-27 but US market hasn't opened yet)
        # Use correlated subquery to get each symbol's latest available date
        overnight_rows = conn.execute("""
            SELECT name, close, change_pct FROM global_market_index_daily g1
            WHERE trade_date = (
                SELECT MAX(trade_date) FROM global_market_index_daily g2
                WHERE g2.symbol = g1.symbol AND g2.trade_date <= ?
            )
            ORDER BY change_pct DESC
        """, (td,)).fetchall()

        trans_rows = conn.execute("""
            SELECT us_theme, a_share_themes_json, signal_strength, direction, reason
            FROM us_a_share_transmission WHERE trade_date=?
            ORDER BY ABS(signal_strength) DESC
        """, (td,)).fetchall()
        news_rows = conn.execute("""
            SELECT category, title, summary, url, source FROM premarket_news
            WHERE trade_date=?
        """, (td,)).fetchall()

    has_overnight = len(overnight_rows) > 0
    has_trans = len(trans_rows) > 0
    has_news = len(news_rows) > 0
    if not (has_overnight or has_trans or has_news):
        return JSONResponse(status_code=404, content={
            "ok": False, "error": {"code": "NO_DATA",
            "message": f"No morning briefing data for trade_date={td}"}})

    data_status = "ok" if (has_overnight and has_trans and has_news) else "partial"

    # ---- Card 1: 隔夜海外
    ov_items = [{
        "name": r["name"],
        "close": to_float(r["close"]),
        "change_pct": round(to_float(r["change_pct"]) or 0, 2),
    } for r in overnight_rows[:6]]
    ov_summary = _overnight_summary(ov_items)

    # ---- Card 2: 题材传导
    tr_items = []
    for r in trans_rows[:limit]:
        try:
            a_themes = json.loads(r["a_share_themes_json"]) if r["a_share_themes_json"] else []
        except (json.JSONDecodeError, TypeError):
            a_themes = []
        sig = to_float(r["signal_strength"])
        # 弱方向信号取负值（文档：正红负绿）
        if r["direction"] == "weak" and sig is not None:
            sig = round(-abs(sig), 2)
        else:
            sig = round(sig, 2) if sig is not None else 0
        tr_items.append({
            "us_theme": r["us_theme"],
            "a_share_themes": a_themes[:3],
            "signal_strength": sig,
            "reason": _clean_sentence(r["reason"] or ""),
        })

    # ---- Card 3: 盘前要闻
    nw_items = _build_news_items(news_rows, limit)

    return {
        "ok": True,
        "trade_date": td,
        "generated_at": now_sh_iso(),
        "data_status": data_status,
        "source": {
            "kind": "sigmx_market_api",
            "tables": ["global_market_index_daily",
                       "us_a_share_transmission", "premarket_news"],
        },
        "cards": {
            "overnight": {"summary": ov_summary, "items": ov_items},
            "transmission": {"items": tr_items},
            "news": {"items": nw_items},
        },
        "publish": _publish_meta(tr_items),
    }


def _overnight_summary(items):
    """根据涨跌家数生成一句盘前话术。"""
    if not items:
        return "隔夜海外数据暂缺。"
    up = sum(1 for i in items if (i["change_pct"] or 0) > 0)
    dn = sum(1 for i in items if (i["change_pct"] or 0) < 0)
    # 找最强方向
    if not items:
        return "隔夜海外分化。"
    strongest = max(items, key=lambda x: abs(x["change_pct"] or 0))
    sname = strongest["name"]
    if up > dn:
        return f"隔夜海外{up}涨{dn}跌，{sname}领涨，盘前关注情绪承接。"
    elif dn > up:
        return f"隔夜海外{up}涨{dn}跌，{sname}偏弱，留意风险释放。"
    return f"隔夜海外{up}涨{dn}跌，分化明显，盘前观察科技线方向。"


# 新闻清洗：过滤垃圾标题 + 去省略号 + 加分类前缀
_NEWS_CATEGORY_PREFIX = {
    "policy": "政策线索",
    "industry": "产业变化",
    "catalyst": "催化方向",
    "risk": "风险提示",
}
_NEWS_GARBAGE = ("股票行情", "走势图", "_频道", "东方财富", "频道 -", "行情_",
                 "数据中心", "下载", "登录", "注册")


def _clean_sentence(text):
    """机械清洗：去省略号、去多余空白、去首尾标点。保留完整句子，不截断、不语义压缩。"""
    if not text:
        return ""
    s = re.sub(r"[…\.]{2,}", "", text)          # 去省略号 ......
    s = re.sub(r"\s+", "", s)                    # 去所有空白
    s = s.strip("。.，,；; ")
    return s


# 开头的来源/记者标识，纯机械去掉（如"财联社7月9日讯（记者 陈抗）"）
_NEWS_SOURCE_PATTERNS = [
    re.compile(r"^财联社\d+月\d+日[讯报]（[^）]*）?"),
    re.compile(r"^财联社[讯报]"),
    re.compile(r"^财新数据[讯报]?"),
    re.compile(r"^[本该]报[讯报]"),
    re.compile(r"^[新华央视][^，。]{0,6}[讯报]"),
]


def _strip_source_prefix(body):
    """去掉 body 开头的来源/电头标识（纯字符串匹配，不做语义判断）。"""
    changed = True
    while changed:
        changed = False
        for pat in _NEWS_SOURCE_PATTERNS:
            new = pat.sub("", body, count=1)
            if new != body:
                body = new
                changed = True
    return body.strip("：:，, ")


def _build_news_items(news_rows, limit):
    """每类取一条，凑够 limit 条。
    每条只做机械清洗（去省略号/来源前缀/空白，保留完整句子，不截断不语义压缩）。
    一句话总结由调用方 LLM 做；本 API 只给干净的结构化原文 + quality 标记。"""
    by_cat = {}
    for r in news_rows:
        cat = r["category"] if r["category"] in _NEWS_CATEGORY_PREFIX else "industry"
        by_cat.setdefault(cat, []).append(r)

    items = []
    seen_keys = set()

    def add(item):
        # 去重：按 title 或 summary
        key = item.get("title") or item.get("summary")
        if key and key in seen_keys:
            return False
        if key:
            seen_keys.add(key)
        items.append(item)
        return True

    # 按 policy/industry/catalyst/risk 顺序，每类挑一条
    for cat in ("policy", "industry", "catalyst", "risk"):
        if cat not in by_cat or len(items) >= limit:
            continue
        best = _pick_clean_news(by_cat[cat])
        if best:
            add(best)
    # 不够 limit 则从剩余条目补（含 skipped 的，但调用方应按 quality 跳过）
    if len(items) < limit:
        for cat in ("policy", "industry", "catalyst", "risk"):
            for r in by_cat.get(cat, []):
                if len(items) >= limit:
                    break
                item = _news_item_from_row(r)
                if item:
                    add(item)
    return items[:limit]


def _news_item_from_row(r):
    """单条新闻 -> 结构化 item。纯机械清洗，不做语义压缩/替换/截断。
    返回字段（按 API 文档）：category / title / summary / source / url / quality。
    - title/summary：各自机械清洗后保留完整原文（去省略号、去来源/电头前缀、去首尾标点、合并空白）。
    - quality：清洗后 title 与 summary 都不达标(为空/仅标点数字/过短) -> "skipped"，
      调用方应跳过、不凑数；否则 "ok"。
    不返回 sentence —— 一句话语义总结由调用方 LLM 生成。
    """
    cat = r["category"] if r["category"] in _NEWS_CATEGORY_PREFIX else "industry"
    raw_title = r["title"] or ""
    raw_summary = r["summary"] or ""

    # title：过滤垃圾标题后再清洗
    title_clean = ""
    if raw_title and not any(g in raw_title for g in _NEWS_GARBAGE):
        title_clean = _strip_source_prefix(_clean_sentence(raw_title))

    # summary：直接清洗
    summary_clean = _strip_source_prefix(_clean_sentence(raw_summary)) if raw_summary else ""

    # quality 判定：title 或 summary 任一达标即 ok
    def usable(s):
        if not s:
            return False
        if len(s) < 6:                      # 过短
            return False
        if re.fullmatch(r"[\d\.\,\s，。、；：]+", s):  # 仅标点/数字
            return False
        return True

    quality = "ok" if (usable(title_clean) or usable(summary_clean)) else "skipped"

    return {
        "category": cat,
        "title": title_clean or None,
        "summary": summary_clean or None,
        "source": r["source"],
        "url": r["url"],
        "quality": quality,
    }


def _pick_clean_news(rows):
    """从一类新闻里挑一条：优先 quality=ok 的，没有则取第一条。"""
    for r in rows:
        item = _news_item_from_row(r)
        if item and item.get("quality") == "ok":
            return item
    for r in rows:
        item = _news_item_from_row(r)
        if item:
            return item
    return None


def _publish_meta(trans_items):
    """根据传导信号生成发布标题。"""
    title = "早盘先看海外传导"
    if trans_items:
        top = trans_items[0]
        if (top["signal_strength"] or 0) > 0:
            title = f"盘前关注{top['a_share_themes'][0] if top['a_share_themes'] else '主线'}承接"
        else:
            title = "隔夜海外偏弱，留意风险释放"
    return {
        "title": title,
        "description": "三张图看盘前重点",
        "hashtags": ["A股", "早盘内参", "盘前要闻", "SigmX", "AI投研"],
    }


def _sigmx_endpoint_list():
    return [
        "/api/v1/market/latest-trade-date",
        "/api/v1/market/overview",
        "/api/v1/market/breadth",
        "/api/v1/market/fund-summary",
        "/api/v1/indices/daily",
        "/api/v1/sectors/fund-flow",
        "/api/v1/sectors/fund-flow/intraday",
        "/api/v1/stocks/hot-pool",
        "/api/v1/stocks/metadata",
        "/api/v1/stocks/daily",
        "/api/v1/stocks/daily-basic",
        "/api/v1/etf/daily",
        "/api/v1/fund/daily",
        "/api/v1/boards/daily",
        "/api/v1/boards/members",
        "/api/v1/quotes/realtime",
        "/api/v1/stocks/fund-flow",
        "/api/v1/stocks/capital-flow",
        "/api/v1/stocks/capital-rank",
        "/api/v1/northbound/flow",
        "/api/v1/stocks/limit-pool",
        "/api/v1/dragon-tiger",
        "/api/v1/hot-list",
        "/api/v1/market/regime",
        "/api/v1/stocks/financial-snapshot",
        "/api/v1/stocks/financial-statement",
        "/api/v1/stocks/eps-forecast",
        "/api/v1/stocks/margin",
        "/api/v1/stocks/block-trade",
        "/api/v1/stocks/holder-num",
        "/api/v1/stocks/dividends",
        "/api/v1/funds/premium",
        "/api/v1/funds/arbitrage-signals",
        "/api/v1/etf/share-size",
        "/api/v1/option-chain",
        "/api/v1/market/stage-snapshot",
        "/api/v1/stocks/fq-factors",
        "/api/v1/stocks/minute",
        "/api/v1/stocks/ticks",
        "/api/v1/stocks/quote5",
        "/api/v1/news/finance/rss-summary",
        "/api/v1/content/morning-briefing-triptych",
    ]


@router.get("/api/v1/health")
def health(request: Request):
    with get_db() as conn:
        td = latest_trade_date(conn)
    info: dict = {
        "status": "healthy",
        "latest_trade_date": td,
        "endpoints": _sigmx_endpoint_list(),
        "data_hub": _is_data_hub_enabled(),
    }
    if _is_data_hub_enabled():
        try:
            from src.data.subscription_store import get_subscription_store
            store = get_subscription_store()
            subs = store.list_all()
            active = sum(1 for s in subs if s.get("active"))
            info["subscriptions"] = active
        except Exception:
            pass
    return info


def _is_data_hub_enabled() -> bool:
    """Return whether Data Hub mode is enabled (API key auth required for remote)."""
    return os.getenv("VIBE_TRADING_DATA_HUB_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def register_sigmx_routes(app: FastAPI) -> None:
    """Mount all /api/v1/* SigmX market-data routes onto the app.

    All /api/v1/* endpoints go through ``_data_hub_auth``: in Data Hub mode,
    remote (non-loopback) requests require a valid API key; loopback and
    non-Data-Hub deployments pass through. See ``_data_hub_auth`` for details.
    """
    app.include_router(router, dependencies=[Depends(_data_hub_auth)])

