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
import re
import ssl
import time
import urllib.request
from typing import Any

import requests

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


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


# ── Layer 6: 基础数据 — mootdx 财务快照 + F10 ──────────────────────


def mootdx_finance(symbol: str) -> dict:
    """mootdx 财务快照 — 37 字段季报数据（不封 IP）。
    返回: {liutongguben, zongguben, eps, bvps, roe, profit, income, ...}
    """
    client = tdx_client()
    return client.finance(symbol=symbol)


def mootdx_f10(symbol: str, category: str = "最新提示") -> str:
    """mootdx F10 文本 — 9 大类公司资料（不封 IP）。
    category: 最新提示/公司概况/财务分析/股东研究/股本结构/资本运作/业内点评/行业分析/公司大事
    """
    client = tdx_client()
    return client.F10(symbol=symbol, name=category) or ""


# ── Layer 6: 基础数据 — 新浪财报三表 ──────────────────────────────


def sina_financial_report(code: str, report_type: str = "lrb", num: int = 8) -> list[dict]:
    """新浪财报三表（直连 quotes.sina.cn，不封 IP）。
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    返回: 按报告期倒序的记录列表，每期含各科目值+同比。
    """
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code, "source": report_type,
        "type": "0", "page": "1", "num": str(num),
    }
    req = urllib.request.Request(url + "?" + "&".join(f"{k}={v}" for k, v in params.items()))
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))

    report_list = data.get("result", {}).get("data", {}).get("report_list", {}) or {}
    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec: dict[str, Any] = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in obj.get("data", []) or []:
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None:
                continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""):
                rec[title + "_同比"] = tongbi
        rows.append(rec)
    return rows


# ── Layer 7: 公告 — 巨潮 cninfo ───────────────────────────────────

_CNINFO_ORGID_MAP: dict[str, str] = {}


def _cninfo_orgid(code: str) -> str:
    """查股票真实 orgId（动态映射表，首次调用时拉取）。"""
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        try:
            req = urllib.request.Request(
                "http://www.cninfo.com.cn/new/data/szse_stock.json",
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                _CNINFO_ORGID_MAP = {
                    s["code"]: s["orgId"]
                    for s in json.loads(r.read()).get("stockList", [])
                }
        except Exception as e:
            logger.warning("巨潮 orgId 映射表拉取失败: %s", e)
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    if code.startswith("6"):
        return f"gssh0{code}"
    elif code.startswith(("8", "4")):
        return f"gsbj0{code}"
    return f"gssz0{code}"


def cninfo_announcements(code: str, page_size: int = 30) -> list[dict]:
    """巨潮公告全文检索（直连 cninfo.com.cn，不封 IP）。
    返回: [{title, type, date, url}]
    """
    from datetime import datetime as _dt

    def _ts_to_date(ts: Any) -> str:
        if isinstance(ts, (int, float)):
            return _dt.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        return str(ts)[:10] if ts else ""

    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    org_id = _cninfo_orgid(code)
    body = (
        f"stock={code},{org_id}&tabName=fulltext&pageSize={page_size}"
        f"&pageNum=1&column=&category=&plate=&seDate=&searchkey=&secid="
        f"&sortName=&sortType=&isHLtitle=true"
    )
    req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.cninfo.com.cn/new/disclosure",
        "Origin": "https://www.cninfo.com.cn",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())

    rows = []
    for item in d.get("announcements", []) or []:
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName", ""),
            "date": _ts_to_date(item.get("announcementTime")),
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}",
        })
    return rows


# ── Layer 3: 信号 — 同花顺热点（题材归因）──────────────────────────


def _normalize_ths_hot_reason_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(item.get("code") or ""),
        "name": str(item.get("name") or ""),
        "reason": str(item.get("reason") or ""),
        "change_pct": _optional_float(item.get("zhangfu")),
        "turnover": _optional_float(item.get("huanshou")),
        "amount": _optional_float(item.get("chengjiaoe")),
        "close": _optional_float(item.get("close")),
        "market": item.get("market"),
    }


def ths_hot_reason(date: str | None = None) -> list[dict]:
    """同花顺当日强势股归因 — 含编辑部人工运营的题材标签（不封 IP）。
    date: 'YYYY-MM-DD' 格式，None=今天
    返回: [{code, name, reason, change_pct, turnover, amount, ...}]
    """
    from datetime import date as _date_mod
    if date is None:
        date = _date_mod.today().strftime("%Y-%m-%d")

    url = (f"http://zx.10jqka.com.cn/event/api/getharden/"
           f"date/{date}/orderby/date/orderway/desc/charset/GBK/")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("gbk"))

    if data.get("errocode", 0) != 0:
        logger.warning("同花顺热点错误: %s", data.get("errormsg", ""))
        return []

    return [_normalize_ths_hot_reason_item(item) for item in (data.get("data") or [])]


# ── Layer 9: ETF 期权 — 新浪（不封 IP）────────────────────────────

_SINA_OPT_HDR = {"Referer": "https://stock.finance.sina.com.cn/", "User-Agent": UA}


def _sina_opt_list(param: str) -> list:
    """新浪 hq.sinajs.cn 取值（GBK，逗号分隔）。"""
    req = urllib.request.Request(
        f"https://hq.sinajs.cn/list={param}", headers=_SINA_OPT_HDR)
    with urllib.request.urlopen(req, timeout=10) as r:
        t = r.read().decode("gbk")
    return t.split('"')[1].split(",") if '"' in t else []


def sina_option_codes(underlying: str = "510050", call: bool = True) -> dict:
    """ETF 期权合约清单。underlying: 510050/510300/588000/510500。
    返回 {月份YYMM: [合约代码,...]}，第一个 key 即近月。
    """
    cate = {"510050": "50ETF", "510300": "300ETF",
            "588000": "科创50ETF", "510500": "500ETF"}.get(underlying, "50ETF")
    url = ("https://stock.finance.sina.com.cn/futures/api/openapi.php/"
           f"StockOptionService.getStockName?exchange=null&cate={cate}")
    try:
        req = urllib.request.Request(url, headers=_SINA_OPT_HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            months = json.loads(r.read())["result"]["data"]["contractMonth"]
    except Exception as e:
        logger.warning("期权月份获取失败: %s", e)
        return {}
    months = [m.replace("-", "")[2:] for m in months[1:]]
    flag = "OP_UP_" if call else "OP_DOWN_"
    out: dict[str, list] = {}
    for m in months:
        codes = [c.replace("CON_OP_", "") for c in _sina_opt_list(f"{flag}{underlying}{m}")
                 if c.startswith("CON_OP_")]
        if codes:
            out[m] = codes
    return out


def _opt_f(x: Any) -> Any:
    try:
        return float(x)
    except Exception:
        return x


def sina_option_tquote(code: str) -> dict:
    """期权 T 型报价。返回 bid/ask/last/open_interest/strike 等。"""
    v = _sina_opt_list(f"CON_OP_{code}")
    if len(v) < 43:
        return {}
    return {
        "bid_vol": _opt_f(v[0]), "bid": _opt_f(v[1]), "last": _opt_f(v[2]),
        "ask": _opt_f(v[3]), "ask_vol": _opt_f(v[4]), "open_interest": _opt_f(v[5]),
        "pct": _opt_f(v[6]), "strike": _opt_f(v[7]), "prev_close": _opt_f(v[8]),
        "name": v[37], "volume": _opt_f(v[41]), "amount": _opt_f(v[42]),
    }


def sina_option_greeks(code: str) -> dict:
    """期权希腊字母 + 隐含波动率。返回 delta/gamma/theta/vega/iv/theory。"""
    raw = _sina_opt_list(f"CON_SO_{code}")
    if len(raw) < 16:
        return {}
    v = [raw[0]] + raw[4:]  # raw[1:4] 是空串，必须跳过
    return {
        "name": v[0], "delta": _opt_f(v[2]), "gamma": _opt_f(v[3]),
        "theta": _opt_f(v[4]), "vega": _opt_f(v[5]),
        "iv": _opt_f(v[6]), "strike": _opt_f(v[10]),
        "last": _opt_f(v[11]), "theory": _opt_f(v[12]),
    }


# ── Layer 3: 信号 — 东财板块归属 / 资金流向 ──────────────────────


def eastmoney_concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属（东财 slist，一次拿全，走 em_get 限流）。
    返回: {total, boards: [{name, code, change_pct, lead_stock}], concept_tags: [...]}
    """
    market_code = 1 if code.startswith("6") else 0
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{market_code}.{code}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    try:
        r = em_get("https://push2.eastmoney.com/api/qt/slist/get",
                   params=params, headers={"User-Agent": UA,
                   "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        d = r.json()
    except Exception as e:
        logger.warning("东财板块归属请求失败: %s", e)
        return {"total": 0, "boards": [], "concept_tags": []}

    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""),
            "lead_stock": it.get("f128", ""),
        })
    return {
        "total": len(boards),
        "boards": boards,
        "concept_tags": [b["name"] for b in boards],
    }


def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """个股资金流向（分钟级，当日盘中）。
    返回: [{time, main_net, small_net, mid_net, large_net, super_net}]
    """
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    try:
        r = em_get(url, params=params, headers={
            "User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        klines = (r.json().get("data") or {}).get("klines") or []
    except Exception as e:
        logger.warning("东财分钟资金流请求失败: %s", e)
        return []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "time": parts[0],
                "main_net": float(parts[1]) if parts[1] != "-" else 0,
                "small_net": float(parts[2]) if parts[2] != "-" else 0,
                "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                "large_net": float(parts[4]) if parts[4] != "-" else 0,
                "super_net": float(parts[5]) if parts[5] != "-" else 0,
            })
    return rows


def stock_fund_flow_120d(code: str) -> list[dict]:
    """个股资金流（日级，最近 120 个交易日）。
    返回: [{date, main_net, small_net, mid_net, large_net, super_net}]
    """
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    try:
        r = em_get(url, params=params, headers={
            "User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
            "Origin": "https://quote.eastmoney.com"}, timeout=15)
        klines = (r.json().get("data") or {}).get("klines") or []
    except Exception as e:
        logger.warning("东财日级资金流请求失败: %s", e)
        return []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0],
                "main_net": float(parts[1]) if parts[1] != "-" else 0,
                "small_net": float(parts[2]) if parts[2] != "-" else 0,
                "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                "large_net": float(parts[4]) if parts[4] != "-" else 0,
                "super_net": float(parts[5]) if parts[5] != "-" else 0,
            })
    return rows


# ── Layer 4: 资金面 — 融资融券 / 大宗交易 / 股东户数 / 分红 ────────

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                         filter_str: str = "", page_size: int = 50,
                         sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询（走 em_get 限流）。"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        logger.warning("东财数据中心 %s 请求失败: %s", report_name, e)
        return []
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


def margin_trading(code: str, page_size: int = 30) -> list[dict]:
    """融资融券明细（日级）。"""
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=page_size, sort_columns="DATE", sort_types="-1",
    )
    return [{
        "date": str(r.get("DATE", ""))[:10],
        "rzye": r.get("RZYE", 0), "rzmre": r.get("RZMRE", 0),
        "rzche": r.get("RZCHE", 0), "rqye": r.get("RQYE", 0),
        "rqmcl": r.get("RQMCL", 0), "rqchl": r.get("RQCHL", 0),
        "rzrqye": r.get("RZRQYE", 0),
    } for r in data]


def block_trade(code: str, page_size: int = 20) -> list[dict]:
    """大宗交易记录。"""
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="TRADE_DATE", sort_types="-1",
    )
    rows = []
    for r in data:
        close = r.get("CLOSE_PRICE") or 0
        deal_price = r.get("DEAL_PRICE") or 0
        premium = ((deal_price / close - 1) * 100) if close else 0
        rows.append({
            "date": str(r.get("TRADE_DATE", ""))[:10],
            "price": deal_price, "close": close,
            "premium_pct": round(premium, 2),
            "vol": r.get("DEAL_VOLUME", 0), "amount": r.get("DEAL_AMT", 0),
            "buyer": r.get("BUYER_NAME", ""), "seller": r.get("SELLER_NAME", ""),
        })
    return rows


def holder_num_change(code: str, page_size: int = 10) -> list[dict]:
    """股东户数变化（季度级）。"""
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="END_DATE", sort_types="-1",
    )
    return [{
        "date": str(r.get("END_DATE", ""))[:10],
        "holder_num": r.get("HOLDER_NUM", 0),
        "change_num": r.get("HOLDER_NUM_CHANGE", 0),
        "change_ratio": r.get("HOLDER_NUM_RATIO", 0),
        "avg_shares": r.get("AVG_FREE_SHARES", 0),
    } for r in data]


def dividend_history(code: str, page_size: int = 20) -> list[dict]:
    """分红送转历史。"""
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    return [{
        "date": str(r.get("EX_DIVIDEND_DATE", ""))[:10],
        "bonus_rmb": r.get("PRETAX_BONUS_RMB", 0),
        "transfer_ratio": r.get("TRANSFER_RATIO", 0),
        "bonus_ratio": r.get("BONUS_RATIO", 0),
        "plan": r.get("ASSIGN_PROGRESS", ""),
    } for r in data]


def _parse_lockup_rows(rows: list[dict[str, Any]], *, trade_date: str) -> dict[str, list[dict]]:
    history: list[dict] = []
    upcoming: list[dict] = []
    for row in rows:
        item = {
            "date": str(row.get("FREE_DATE") or "")[:10],
            "type": str(row.get("FREE_SHARES_TYPE") or ""),
            "shares": _optional_float(row.get("FREE_SHARES")),
            "able_shares": _optional_float(row.get("ABLE_FREE_SHARES")),
            "ratio": _optional_float(row.get("FREE_RATIO")),
        }
        if not item["date"]:
            continue
        (history if item["date"] <= trade_date else upcoming).append(item)
    return {"history": history, "upcoming": upcoming}


def lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> dict:
    """限售解禁日历。返回: {history: [...], upcoming: [...]}"""
    from datetime import datetime as _dt, timedelta as _td
    start = (_dt.strptime(trade_date, "%Y-%m-%d") - _td(days=365)).strftime("%Y-%m-%d")
    end = (_dt.strptime(trade_date, "%Y-%m-%d") + _td(days=forward_days)).strftime("%Y-%m-%d")
    data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{start}\')(FREE_DATE<=\'{end}\')',
        page_size=50, sort_columns="FREE_DATE", sort_types="-1",
    )
    return _parse_lockup_rows(data, trade_date=trade_date)


# ── Layer 8: 打板 — 涨停池 / 炸板 / 跌停 / 昨日涨停 ──────────────

_ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _fmt_zt_time(t: Any) -> str:
    s = str(t).zfill(6)
    return f"{s[0:2]}:{s[2:4]}:{s[4:6]}"


def _em_zt_api(endpoint: str, sort: str, date: str) -> list[dict]:
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": _ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": sort, "date": date}
    try:
        r = em_get(url, params=params, headers={
            "User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception as e:
        logger.warning("涨停板池 %s 请求失败: %s", endpoint, e)
        return []


def em_zt_pool(date: str) -> list[dict]:
    """涨停池。date=YYYYMMDD。"""
    out = []
    for p in _em_zt_api("getTopicZTPool", "fbt:asc", date):
        zttj = p.get("zttj") or {}
        out.append({
            "code": p["c"], "name": p["n"],
            "price": p["p"] / 1000, "pct": round(p["zdp"], 2),
            "amount": p["amount"], "float_cap": p["ltsz"],
            "turnover": round(p["hs"], 2), "limit_days": p["lbc"],
            "first_seal": _fmt_zt_time(p["fbt"]),
            "last_seal": _fmt_zt_time(p["lbt"]),
            "seal_fund": p["fund"], "break_times": p["zbc"],
            "industry": p.get("hybk", ""),
            "zt_stat": f'{zttj.get("days", "?")}天{zttj.get("ct", "?")}板',
        })
    return out


def em_zb_pool(date: str) -> list[dict]:
    """炸板池。"""
    out = []
    for p in _em_zt_api("getTopicZBPool", "fbt:asc", date):
        zttj = p.get("zttj") or {}
        out.append({
            "code": p["c"], "name": p["n"],
            "price": p["p"] / 1000, "limit_price": p["ztp"] / 1000,
            "pct": round(p["zdp"], 2), "turnover": round(p["hs"], 2),
            "first_seal": _fmt_zt_time(p["fbt"]),
            "break_times": p["zbc"], "amplitude": round(p["zf"], 2),
            "speed": round(p["zs"], 2), "industry": p.get("hybk", ""),
            "zt_stat": f'{zttj.get("days", "?")}天{zttj.get("ct", "?")}板',
        })
    return out


def em_dt_pool(date: str) -> list[dict]:
    """跌停池。"""
    out = []
    for p in _em_zt_api("getTopicDTPool", "fund:asc", date):
        out.append({
            "code": p["c"], "name": p["n"],
            "price": p["p"] / 1000, "pct": round(p["zdp"], 2),
            "turnover": round(p["hs"], 2), "pe": p.get("pe"),
            "seal_fund": p["fund"], "last_seal": _fmt_zt_time(p["lbt"]),
            "board_amount": p.get("fba"), "dt_days": p.get("days"),
            "open_times": p.get("oc"), "industry": p.get("hybk", ""),
        })
    return out


def em_yzt_pool(date: str) -> list[dict]:
    """昨日涨停池（算晋级率/赚钱效应）。"""
    out = []
    for p in _em_zt_api("getYesterdayZTPool", "zs:desc", date):
        zttj = p.get("zttj") or {}
        out.append({
            "code": p["c"], "name": p["n"],
            "price": p["p"] / 1000, "pct": round(p["zdp"], 2),
            "turnover": round(p["hs"], 2),
            "amplitude": round(p["zf"], 2), "speed": round(p["zs"], 2),
            "y_first_seal": _fmt_zt_time(p["yfbt"]),
            "y_limit_days": p["ylbc"], "industry": p.get("hybk", ""),
            "zt_stat": f'{zttj.get("days", "?")}天{zttj.get("ct", "?")}板',
        })
    return out


def ths_limit_up_pool(date: str) -> list[dict]:
    """同花顺涨停揭秘（涨停原因 + 封板质量）。date=YYYYMMDD。"""
    from datetime import datetime as _dt
    url = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
    params = {
        "page": 1, "limit": 200,
        "field": "199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004",
        "filter": "HS,GEM2STAR", "order_field": "330324",
        "order_type": "0", "date": date,
    }
    try:
        req = urllib.request.Request(url + "?" + "&".join(f"{k}={v}" for k, v in params.items()))
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            info = (json.loads(r.read()).get("data") or {}).get("info") or []
    except Exception as e:
        logger.warning("同花顺涨停揭秘请求失败: %s", e)
        return []
    out = []
    for it in info:
        ft = it.get("first_limit_up_time")
        out.append({
            "code": it.get("code"), "name": it.get("name"),
            "price": it.get("latest"), "pct": it.get("change_rate"),
            "reason": it.get("reason_type", ""),
            "board_type": it.get("limit_up_type", ""),
            "seal_rate": it.get("limit_up_suc_rate"),
            "break_times": it.get("open_num") or 0,
            "seal_amount": it.get("order_amount"),
            "high_days": it.get("high_days", ""),
            "first_time": _dt.fromtimestamp(int(ft)).strftime("%H:%M:%S") if ft else "",
            "is_again": it.get("is_again_limit"),
        })
    return out


def limit_up_sentiment(date: str) -> dict:
    """打板情绪速算 — 炸板率 / 连板高度 / 连板梯队。"""
    zt = em_zt_pool(date)
    zb = em_zb_pool(date)
    yzt = em_yzt_pool(date)
    touched = len(zt) + len(zb)
    fail_rate = round(len(zb) / touched * 100, 2) if touched else 0
    promoted = sum(1 for s in zt if s.get("limit_days", 0) >= 2)
    promotion_rate = round(promoted / len(yzt) * 100, 2) if yzt else 0
    ladder: dict[int, list] = {}
    for s in zt:
        d = s.get("limit_days", 1)
        ladder.setdefault(d, []).append({"code": s["code"], "name": s["name"]})
    return {
        "limit_up_count": len(zt),
        "fail_count": len(zb),
        "fail_rate": fail_rate,
        "max_height": max(ladder.keys()) if ladder else 0,
        "promotion_rate": promotion_rate,
        "ladder": {str(k): len(v) for k, v in sorted(ladder.items(), reverse=True)},
    }


# ── Layer 10: 舆情 — 同花顺热榜 / 东财人气榜 ──────────────────────


def _normalize_ths_hot_list_item(item: dict[str, Any]) -> dict[str, Any]:
    tags = item.get("tag") or {}
    return {
        "code": str(item.get("code") or ""),
        "name": str(item.get("name") or ""),
        "rank": item.get("order") or 0,
        "hot_value": _optional_float(item.get("rate")),
        "change_pct": _optional_float(item.get("rise_and_fall")),
        "rank_change": item.get("hot_rank_chg") or 0,
        "tags": json.dumps(tags, ensure_ascii=False, sort_keys=True),
    }


def ths_hot_list(limit: int = 30) -> list[dict]:
    """同花顺热榜（人气值 + 概念标签 + 排名变化）。"""
    url = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
    params = {"stock_type": "a", "type": "hour", "list_type": "normal"}
    try:
        req = urllib.request.Request(url + "?" + "&".join(f"{k}={v}" for k, v in params.items()))
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        logger.warning("同花顺热榜请求失败: %s", e)
        return []
    items = (d.get("data") or {}).get("stock_list") or []
    return [_normalize_ths_hot_list_item(item) for item in items[:limit]]


def eastmoney_popularity(page_size: int = 30) -> list[dict]:
    """东财人气榜。"""
    url = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
    body = json.dumps({
        "appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
        "pageNo": 1, "pageSize": page_size,
    }).encode()
    try:
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "User-Agent": UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        logger.warning("东财人气榜请求失败: %s", e)
        return []
    result = []
    for it in (d.get("data") or []):
        sc = it.get("sc", "")  # e.g. "SZ002384"
        code = sc[2:] if len(sc) > 2 else sc
        result.append({
            "code": code,
            "market": sc[:2] if len(sc) > 2 else "",
            "rank": it.get("rk", 0),
            "rank_change": it.get("rc", 0),
            "history_rank_change": it.get("hisRc", 0),
        })
    return result


# ── Layer 2: 研报 — 同花顺一致预期 EPS（不依赖东财）───────────────


def ths_eps_forecast(code: str) -> list[dict]:
    """同花顺机构一致预期 EPS（直连 basic.10jqka.com.cn，不依赖东财）。
    返回: [{year, count, min_eps, mean_eps, max_eps, net_profit}]
    均值 = 机构一致预期 EPS。预测机构数 < 3 的要谨慎。
    """
    import re as _re
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("gbk", errors="replace")
    except Exception as e:
        logger.warning("同花顺一致预期请求失败: %s", e)
        return []

    # 提取汇总预测: "预测2026年每股收益 68.83 元"
    summary_match = _re.search(r'预测(\d{4})年每股收益.*?<strong>([\d.]+)</strong>', html)

    # 提取表格数据: forecast div 里的 td 序列
    # 格式: 机构数, min, mean, max, net_profit, 机构数, min, mean, max, net_profit...
    forecast_match = _re.search(r'id="forecast".*?</div>\s*<div', html, _re.DOTALL)
    if not forecast_match:
        # 尝试提取 forecastdetail
        forecast_match = _re.search(r'id="forecast"(.*?)(?:id="forecastdetail"|</div>\s*</div>)', html, _re.DOTALL)

    rows = []
    if forecast_match:
        block = forecast_match.group(0) if forecast_match.lastindex else forecast_match.group()
        # 找年度标题行 (含 "年" 的文本)
        # 提取 td 内容
        tds = _re.findall(r'<td[^>]*>(.*?)</td>', block)
        # 清理 HTML 标签
        clean_tds = []
        for td in tds:
            val = _re.sub(r'<[^>]+>', '', td).strip()
            clean_tds.append(val)

        # 每 5 个 td 一组: 机构数, min, mean, max, net_profit
        for td in clean_tds:
            if td and "tc" in td:
                continue  # skip class-only markers
        # 按年度分组：先找所有包含年份的行
        year_blocks = _re.split(r'(?:汇总|预测.*?每股收益)', block)
        for idx, yb in enumerate(year_blocks[1:], 1):  # skip before-first
            ym = _re.search(r'(\d{4})', yb)
            if not ym:
                continue
            year = ym.group(1)
            ytds = _re.findall(r'<td[^>]*>(.*?)</td>', yb)
            vals = [_re.sub(r'<[^>]+>', '', v).strip() for v in ytds]
            # 找数字组: count, min, mean, max, profit
            nums = [v for v in vals if v and _re.match(r'^[\d.-]+$', v)]
            if len(nums) >= 4:
                rows.append({
                    "year": year,
                    "count": int(float(nums[0])) if nums[0] else 0,
                    "min_eps": float(nums[1]) if nums[1] else 0,
                    "mean_eps": float(nums[2]) if nums[2] else 0,
                    "max_eps": float(nums[3]) if nums[3] else 0,
                    "net_profit": float(nums[4]) if len(nums) > 4 and nums[4] else 0,
                })

    # fallback: 从 summary 取当年预测
    if not rows and summary_match:
        rows.append({
            "year": summary_match.group(1),
            "count": 0,
            "min_eps": 0,
            "mean_eps": float(summary_match.group(2)),
            "max_eps": 0,
            "net_profit": 0,
        })

    return rows


# ── Layer 3: 信号 — 同花顺北向资金 ────────────────────────────────


def hsgt_realtime() -> list[dict]:
    """同花顺沪深股通当日实时分钟流向（不封 IP）。
    返回: [{time, hgt_yi(沪股通累计净买入亿), sgt_yi(深股通累计净买入亿)}]
    ⚠️ 深股通近期上游披露收紧，sgt 仅供参考；沪股通 hgt 可靠。
    """
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        logger.warning("同花顺北向资金请求失败: %s", e)
        return []
    times = d.get("time", [])
    hgt = d.get("hgt", [])
    sgt = d.get("sgt", [])
    return [
        {
            "time": t,
            "hgt_yi": hgt[i] if i < len(hgt) else None,
            "sgt_yi": sgt[i] if i < len(sgt) else None,
        }
        for i, t in enumerate(times)
    ]


# ── Layer 1: 行情 — 百度 K 线（自带 MA5/10/20）─────────────────────


def _parse_baidu_kline_payload(payload: dict[str, Any]) -> dict[str, list]:
    result = payload.get("Result")
    if not isinstance(result, dict):
        return {"keys": [], "rows": []}
    market_data = result.get("newMarketData")
    if not isinstance(market_data, dict):
        return {"keys": [], "rows": []}
    keys = market_data.get("keys") or []
    raw_rows = market_data.get("marketData") or ""
    if isinstance(raw_rows, str):
        rows = [row for row in raw_rows.split(";") if row]
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        rows = []
    return {"keys": list(keys), "rows": rows}


def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通 K 线 — 自带 ma5/ma10/ma20 均价（不封 IP）。
    返回: {keys: [...], rows: [[...], ...]}
    """
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": code, "start_time": start_time, "ktype": "1",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url + "?" + qs, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        logger.warning("百度K线请求失败: %s", e)
        return {"keys": [], "rows": []}
    return _parse_baidu_kline_payload(d)


# ── Layer 10: 舆情 — 互动易问答（巨潮官方）────────────────────────


def cninfo_irm(code: str, page_size: int = 30) -> list[dict]:
    """互动易问答（深沪统一走巨潮，不封 IP）。
    返回: [{code, company, question, answer, answerer, ask_time}]
    """
    from datetime import datetime as _dt
    try:
        body = f"keyWord={code}".encode()
        req = urllib.request.Request(
            "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
            data=body, method="POST",
            headers={"User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d1 = json.loads(r.read()).get("data") or []
        if not d1:
            return []
        org_id = d1[0].get("secid")
    except Exception as e:
        logger.warning("互动易 orgId 查询失败: %s", e)
        return []
    try:
        qs = (f"_t=1&stockcode={code}&orgId={org_id}&pageSize={page_size}"
              f"&pageNum=1&keyWord=&startDay=&endDay=")
        req = urllib.request.Request(
            f"https://irm.cninfo.com.cn/newircs/company/question?{qs}",
            method="POST",
            headers={"User-Agent": UA, "Content-Length": "0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read()).get("rows") or []
    except Exception as e:
        logger.warning("互动易问答请求失败: %s", e)
        return []
    out = []
    for it in rows:
        pd = it.get("pubDate")
        out.append({
            "code": it.get("stockCode"),
            "company": it.get("companyShortName", ""),
            "question": it.get("mainContent", ""),
            "answer": it.get("attachedContent"),
            "answerer": it.get("attachedAuthor", ""),
            "ask_time": _dt.fromtimestamp(pd / 1000).strftime("%Y-%m-%d %H:%M") if pd else "",
        })
    return out


# ── Layer 5: 新闻 — 财联社电报（修复版 v1 API + 签名）─────────────


def cls_telegraph(page_size: int = 50) -> list[dict]:
    """财联社电报（全市场实时快讯，v1 API + 本地签名零 key）。
    返回: [{title, content, time}]
    """
    import hashlib
    params = {
        "appName": "CailianpressWeb", "os": "web", "sv": "7.7.5",
        "last_time": "", "refresh_type": "1", "rn": str(page_size),
    }
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.cls.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        logger.warning("财联社电报请求失败: %s", e)
        return []
    if d.get("errno") and d["errno"] != 0:
        logger.warning("财联社返回错误: errno=%s", d.get("errno"))
        return []
    from datetime import datetime as _dt
    rows = []
    for item in (d.get("data") or {}).get("roll_data") or []:
        ts = item.get("ctime")
        t = _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        rows.append({
            "title": item.get("title", "") or item.get("brief", ""),
            "content": item.get("content", "") or item.get("brief", ""),
            "time": t,
        })
    return rows


# ── Layer 5: 新闻 — 东财全球资讯（7×24 修复版）───────────────────


def eastmoney_global_news(page_size: int = 50) -> list[dict]:
    """东财全球财经资讯（7×24 滚动，走 em_get 限流）。"""
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724",
        "fastColumn": "102", "sortEnd": "",
        "pageSize": str(page_size),
    }
    try:
        r = em_get(url, params=params, headers={
            "User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"}, timeout=10)
        d = r.json()
    except Exception as e:
        logger.warning("东财全球资讯请求失败: %s", e)
        return []
    return [{
        "title": a.get("title", ""),
        "summary": (a.get("summary") or "")[:200],
        "time": a.get("showTime", ""),
    } for a in (d.get("data") or {}).get("fastNewsList") or []]


# ── Layer 5: 新闻 — 东财个股新闻 ──────────────────────────────────


def _parse_eastmoney_stock_news_payload(payload: dict[str, Any]) -> list[dict]:
    articles = (payload.get("result") or {}).get("cmsArticleWebOld") or []
    if isinstance(articles, dict):
        articles = articles.get("list") or []
    if not isinstance(articles, list):
        return []
    return [
        {
            "title": _strip_html(article.get("title")),
            "summary": _strip_html(article.get("content"))[:200],
            "date": str(article.get("date") or ""),
            "source": str(article.get("mediaName") or ""),
            "url": str(article.get("url") or ""),
        }
        for article in articles
        if isinstance(article, dict)
    ]


def eastmoney_stock_news(code: str, page_size: int = 20) -> list[dict]:
    """东财个股新闻流（走 em_get 限流）。"""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner = json.dumps({
        "uid": "", "keyword": code, "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": page_size,
            "preTag": "", "postTag": ""}},
    })
    params = {"cb": "jQuery", "param": inner}
    try:
        r = em_get(url, params=params, timeout=10)
        text = r.text
        start = text.index("(") + 1
        end = text.rindex(")")
        d = json.loads(text[start:end])
    except Exception as e:
        logger.warning("东财个股新闻请求失败: %s", e)
        return []
    return _parse_eastmoney_stock_news_payload(d)
