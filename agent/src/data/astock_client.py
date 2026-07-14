"""A股多源数据客户端 — 集成 a-stock-data 项目的核心能力。

设计原则：
  - mootdx/腾讯 不封 IP → 优先用
  - 东财 有内置限流防封 → 用于其独有数据
  - 交易所官方/新浪 → 备用源降级

来源：https://github.com/simonlin1212/a-stock-data (V3.4.0)
"""

from __future__ import annotations

import json
import logging
import random
import ssl
import time
import urllib.request
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


# ── 东财统一请求入口（限流 + 重试 + Keep-Alive）─────────────────────

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _em_adapter = HTTPAdapter(max_retries=Retry(
        total=3, connect=3, backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
    EM_SESSION.mount("https://", _em_adapter)
    EM_SESSION.mount("http://", _em_adapter)
except Exception:
    pass

EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs) -> requests.Response:
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


# ── mootdx 客户端（规避 0.11.x BESTIP bug）─────────────────────────

_TDX_SERVERS = [
    ("119.147.212.81", 7709),
    ("112.74.214.43", 7727),
    ("221.231.141.60", 7709),
]


def tdx_client(market: str = "std"):
    """创建 mootdx 客户端，规避 0.11.x BESTIP.HQ 空串 bug。"""
    from mootdx.quotes import Quotes

    for ip, port in _TDX_SERVERS:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((ip, port))
            s.close()
            return Quotes.factory(market=market, server=ip, port=port)
        except Exception:
            continue
    # 全部不可达 → 回退 mootdx 自带 bestip 测速选优
    return Quotes.factory(market=market)


# ── 腾讯财经实时行情（不封 IP）─────────────────────────────────────


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """批量拉取腾讯财经实时行情。
    codes: ["688017", "300476", "000001"]
    也支持指数: ["000001", "000300", "399006"]
    也支持ETF: ["510050", "510300"]
    """
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
        }
    return result


# ── 腾讯指数行情（不封 IP）────────────────────────────────────────


def tencent_index_quote(codes: list[str] | None = None) -> list[dict]:
    """腾讯指数行情。codes 默认为主要指数。
    注意：指数代码需要 sh/sz/bj 前缀（如 sh000001=上证指数），
    不传前缀时 000001 会被当成平安银行。
    """
    INDEX_PREFIX_MAP = {
        "000001": "sh", "000300": "sh", "000905": "sh",
        "000852": "sh", "000688": "sh",
        "399001": "sz", "399006": "sz", "399005": "sz",
        "899050": "bj",
    }

    if codes is None:
        codes = ["000001", "399001", "399006", "000300", "000905", "000852", "000688", "899050"]

    name_map = {
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
        "000300": "沪深300",
        "000905": "中证500",
        "000852": "中证1000",
        "000688": "科创50",
        "899050": "北证50",
    }

    # 自动加前缀
    prefixed = []
    bare_to_full = {}
    for c in codes:
        bare = c.replace("sh", "").replace("sz", "").replace("bj", "").replace(".", "").upper()
        prefix = INDEX_PREFIX_MAP.get(bare, c[:2] if len(c) > 2 else "sh")
        full_code = f"{prefix}{bare}"
        prefixed.append(full_code)
        bare_to_full[bare] = full_code

    # 请求腾讯
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    # 解析结果
    qq = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]  # strip sh/sz/bj prefix
        qq[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
        }

    result = []
    for bare in codes:
        bare = bare.replace("sh", "").replace("sz", "").replace("bj", "").replace(".", "").upper()
        q = qq.get(bare, {})
        if q:
            full = bare_to_full.get(bare, f"sh{bare}")
            suffix = ".SH" if full.startswith("sh") else ".SZ" if full.startswith("sz") else ".BJ"
            result.append({
                "code": bare + suffix,
                "name": q.get("name", name_map.get(bare, bare)),
                "price": q.get("price", 0),
                "change_pct": q.get("change_pct", 0),
                "open": q.get("open", 0),
                "high": q.get("high", 0),
                "low": q.get("low", 0),
            })
    return result


# ── 备用源：沪深交易所官方龙虎榜 ──────────────────────────────────


def dragon_tiger_backup(trade_date: str) -> dict:
    """龙虎榜官方备用源（东财被封时用）：上交所+深交所官方，零鉴权。"""
    out: dict[str, Any] = {"date": trade_date, "sse_raw": "", "szse": []}

    # 深交所
    su = (f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON"
          f"&CATALOGID=1842_xxpl&TABKEY=tab1&txtStart={trade_date}&txtEnd={trade_date}&random=0.9")
    try:
        req = urllib.request.Request(su, headers={
            "User-Agent": UA,
            "Referer": "https://www.szse.cn/disclosure/supervision/dealinfo/index.html"})
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
            d = json.loads(r.read())
        for row in d[0].get("data", []):
            out["szse"].append({
                "code": row.get("zqdm"), "name": row.get("zqjc"),
                "amount": row.get("cjje"), "reason": row.get("plyy")})
    except Exception as e:
        logger.warning("深交所龙虎榜备用源失败: %s", e)

    # 上交所
    eu = (f"https://query.sse.com.cn/infodisplay/showTradePublicFile.do?"
          f"jsonCallBack=cb&isPagination=false&dateTx={trade_date}")
    try:
        req = urllib.request.Request(eu, headers={
            "User-Agent": UA,
            "Referer": "https://www.sse.com.cn/disclosure/diclosure/public/"})
        with urllib.request.urlopen(req, timeout=15) as r:
            t = r.read().decode("utf-8", "ignore")
        out["sse_raw"] = "\n".join(
            json.loads(t[t.index("(") + 1:t.rindex(")")]).get("fileContents", []))
    except Exception as e:
        logger.warning("上交所龙虎榜备用源失败: %s", e)

    return out


# ── 备用源：新浪资金流 ────────────────────────────────────────────


def fund_flow_backup(code: str, days: int = 60) -> list:
    """个股资金流备用源（东财被封时用）：新浪，日度四档单净额。"""
    pre = ("sh" if code.startswith(("6", "9"))
           else "bj" if code.startswith("8")
           else "sz") + code
    u = (f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
         f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}")
    req = urllib.request.Request(u, headers={
        "User-Agent": UA, "Referer": "https://finance.sina.com.cn/"})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode("utf-8", "ignore")
    arr = json.loads(t[t.index("["):t.rindex("]") + 1])
    return [{"date": x.get("opendate"), "close": x.get("trade"),
             "net_amount": x.get("netamount"), "turnover": x.get("turnover")} for x in arr]


# ── 新浪指数实时行情（验证可用）───────────────────────────────────


def sina_index_spot() -> list[dict]:
    """新浪实时指数行情。已验证可用（HTTP 200）。"""
    url = "https://hq.sinajs.cn/list=sh000001,sz399001,sz399006,sh000300,sh000905,sh000852,sh000688,bj899050"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://finance.sina.com.cn/"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read().decode("gbk")

    name_map = {
        "sh000001": ("000001.SH", "上证指数"),
        "sz399001": ("399001.SZ", "深证成指"),
        "sz399006": ("399006.SZ", "创业板指"),
        "sh000300": ("000300.SH", "沪深300"),
        "sh000905": ("000905.SH", "中证500"),
        "sh000852": ("000852.SH", "中证1000"),
        "sh000688": ("000688.SH", "科创50"),
        "bj899050": ("899050.BJ", "北证50"),
    }
    result = []
    for line in data.strip().split("\n"):
        m = None
        import re
        m = re.match(r'var hq_str_(\w+)="(.+)"', line)
        if not m:
            continue
        sina_code = m.group(1)
        fields = m.group(2).split(",")
        if len(fields) < 4 or sina_code not in name_map:
            continue
        code, name = name_map[sina_code]
        prev_close = float(fields[2]) if fields[2] else 0
        current = float(fields[3]) if fields[3] else 0
        pct_chg = round((current - prev_close) / prev_close * 100, 4) if prev_close else 0
        result.append({
            "code": code, "name": name,
            "close": current, "pct_chg": pct_chg,
            "open": float(fields[1]) if fields[1] else 0,
            "high": float(fields[4]) if fields[4] else 0,
            "low": float(fields[5]) if fields[5] else 0,
        })
    return result
