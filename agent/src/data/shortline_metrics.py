"""短线计算型快照的纯计算层（Vibe-AStock duanxian 语义移植）。

输入是 market.db 池表的行 dict（列名即 zt_pool/zb_pool/dt_pool/yzt_pool 的
建表列），输出是可直接落 shortline_snapshot.payload_json 的 dict。本模块
无 IO、无网络——所有数据在同步管道里已经落库（东财池由 ``zt_pool``
数据集一次拉五表，ths 涨停揭秘同步含 reason）。

单位约定（沿用 VA）：比例一律小数（3 位），涨跌幅 %（2 位），计数为只/板。
关键口径：
- 连板数一律用东财 ``limit_days``（lbc，反包票=1），展示标签用 zt_stat
- 晋级 = 昨天该档的 code 今天还在涨停池
- 炸板率分母 = 涨停 + 炸板
- 制度随日期变：创业板 2020-08-24 前 10%；主板 ST 2026-07-06 前 5% 后 10%
"""

from __future__ import annotations

import statistics
from typing import Any

# 制度分界日（VA 常量）：创业板注册制 20% 起始日 / 主板 ST 涨幅新规起始日。
CHINEXT_20PCT_FROM = "2020-08-24"
ST_10PCT_FROM = "2026-07-06"

# tushare daily_basic.total_mv 单位是万元（原值透传入库），500 亿 = 5_000_000 万。
BIGCAP_TOTAL_MV_WAN = 5_000_000

# 同花顺 reason 里的泛属性词：不是题材，归组时过滤（VA _GENERIC）。
_GENERIC_REASON_WORDS = ("国企改革", "破净", "国资", "国企", "板块")
_MAX_REASON_TAGS = 4
_MAX_REASON_TOTAL_LEN = 40

# 反包标签："3天2板" / "3/2" 形态。
_ZT_STAT_RE_PAIR = ("天", "/")


# ---------------------------------------------------------------------------
# 制度规则工具
# ---------------------------------------------------------------------------

def _norm_name(name: Any) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", str(name or ""))


def is_st(name: Any) -> bool:
    return "ST" in _norm_name(name).upper()


def board_of(code: str, name: Any) -> str:
    """制度分类：北交所 / 20cm / 20cm(ST) / 主板ST / 10cm。"""
    code = str(code or "").zfill(6)
    if code[:2] in ("43", "83", "87", "88", "92"):
        return "北交所"
    if code[:3] in ("300", "301", "302", "688", "689"):
        return "20cm(ST)" if is_st(name) else "20cm"
    if is_st(name):
        return "主板ST"
    return "10cm"


def limit_pct(code: str, name: Any, day: str) -> float:
    """该股在 day 当日的涨停幅度（%）。创业板 2020-08-24 前算 10。"""
    code = str(code or "").zfill(6)
    if code[:2] in ("43", "83", "87", "88", "92"):
        return 30.0
    if code.startswith("30"):
        return 20.0 if day >= CHINEXT_20PCT_FROM else 10.0
    if code[:3] in ("688", "689"):
        return 20.0
    if is_st(name):
        return 5.0 if day < ST_10PCT_FROM else 10.0
    return 10.0


def stat_boards(zt_stat: Any, boards: int) -> int:
    """zt_stat "N天M板"/"N/M" 的有效高度 M；解析不出回退 boards。"""
    import re
    m = re.search(r"(\d+)\s*(?:天|/)\s*(\d+)", str(zt_stat or ""))
    if m:
        return int(m.group(2))
    return int(boards or 1)


def board_label(zt_stat: Any, boards: int) -> str:
    """展示标签：days>ct 反包写「N天M板」，否则「M板」。"""
    import re
    m = re.search(r"(\d+)\s*(?:天|/)\s*(\d+)", str(zt_stat or ""))
    if m:
        days, ct = int(m.group(1)), int(m.group(2))
        return f"{days}天{ct}板" if days > ct else f"{ct}板"
    return f"{int(boards or 1)}板"


def is_limit_up_row(price: Any, limit_price: Any, ret: Any,
                    code: str, name: Any, day: str) -> bool | None:
    """三值判定：现价==涨停价（按分）优先；缺价按 ret≥幅度-0.3；都缺 None。"""
    try:
        if price is not None and limit_price is not None:
            return round(float(price) * 100) == round(float(limit_price) * 100)
    except (TypeError, ValueError):
        pass
    try:
        if ret is not None:
            return float(ret) >= limit_pct(code, name, day) - 0.3
    except (TypeError, ValueError):
        pass
    return None


def is_limit_down_row(ret: Any, code: str, name: Any, day: str) -> bool | None:
    try:
        if ret is not None:
            return float(ret) <= -(limit_pct(code, name, day) - 0.3)
    except (TypeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------

def _rets(rows: list[dict]) -> list[float]:
    out = []
    for r in rows:
        try:
            if r.get("pct") is not None:
                out.append(float(r["pct"]))
        except (TypeError, ValueError):
            continue
    return out


def _r2(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _r3(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


def _pct(rets: list[float]) -> dict:
    if not rets:
        return {"available": False, "sample": 0,
                "avg": None, "median": None, "positive_rate": None}
    return {
        "available": True,
        "sample": len(rets),
        "avg": _r2(sum(rets) / len(rets)),
        "median": _r2(statistics.median(rets)),
        "positive_rate": _r3(sum(1 for x in rets if x > 0) / len(rets)),
    }


def _seal_minute(first_seal: Any) -> int | None:
    t = str(first_seal or "").replace(":", "")
    if len(t) >= 4 and t[:4].isdigit():
        return int(t[:4])
    return None


def _group_by_board(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(board_of(r.get("code"), r.get("name")), []).append(r)
    return out


# ---------------------------------------------------------------------------
# 1. emotion 情绪四项
# ---------------------------------------------------------------------------

def build_emotion(trade_date: str, prev_date: str | None,
                  zt_rows: list[dict], prev_zt_rows: list[dict],
                  yzt_rows: list[dict]) -> dict:
    zt_codes = {str(r.get("code") or "") for r in zt_rows}

    # ① 赚钱效应：昨日涨停股今日表现（settled 源 = yzt 池当日 pct）。
    rets = _rets(yzt_rows)
    expected = len(yzt_rows)
    if rets:
        again = sum(1 for r in yzt_rows if str(r.get("code") or "") in zt_codes) \
            if zt_rows else \
            sum(1 for r in yzt_rows if is_limit_up_row(
                r.get("price"), r.get("limit_price"), r.get("pct"),
                r.get("code"), r.get("name"), trade_date) is True)
        money_effect = {
            "available": True, "prev_date": prev_date, "source": "settled",
            "sample": len(rets), "expected_sample": expected,
            "coverage_rate": _r3(len(rets) / expected) if expected else None,
            "partial": len(rets) < expected,
            "avg": _r2(sum(rets) / len(rets)),
            "median": _r2(statistics.median(rets)),
            "positive_rate": _r3(sum(1 for x in rets if x > 0) / len(rets)),
            "limit_up_again_rate": _r3(again / len(rets)),
        }
    else:
        money_effect = {"available": False, "prev_date": prev_date,
                        "reason": "昨日涨停池无数据"}

    # ② 晋级率：prev 日 zt 按 boards 分档，promoted = 今天还在 zt 池。
    if prev_zt_rows and zt_rows:
        def tier_of(b: int) -> str:
            return "1进2" if b == 1 else ("2进3" if b == 2 else "3板以上晋级")
        tiers: dict[str, dict] = {}
        overall_base = overall_promoted = 0
        for r in prev_zt_rows:
            key = tier_of(int(r.get("limit_days") or 1))
            t = tiers.setdefault(key, {"base": 0, "promoted": 0})
            t["base"] += 1
            overall_base += 1
            if str(r.get("code") or "") in zt_codes:
                t["promoted"] += 1
                overall_promoted += 1
        for t in tiers.values():
            t["rate"] = _r3(t["promoted"] / t["base"]) if t["base"] else None
        promotion = {
            "available": True, "prev_date": prev_date, "tiers": tiers,
            "overall": {"base": overall_base, "promoted": overall_promoted,
                        "rate": _r3(overall_promoted / overall_base) if overall_base else None},
            "limit_up_count": len(zt_rows),
            "prev_limit_up_count": len(prev_zt_rows),
        }
    else:
        promotion = {"available": False, "reason": "昨日/今日涨停池缺一"}

    # ③ 连板溢价：prev 日 2 板以上个股今日表现（yzt.y_limit_days>=2 的行）。
    hi_rows = [r for r in yzt_rows if int(r.get("y_limit_days") or 1) >= 2]
    hi_rets = _rets(hi_rows)
    if hi_rets:
        base = _pct(hi_rets)
        consec_premium = {
            "available": True, "prev_date": prev_date,
            "sample": base["sample"], "avg": base["avg"],
            "median": base["median"], "positive_rate": base["positive_rate"],
        }
    elif hi_rows:
        consec_premium = {"available": False, "prev_date": prev_date,
                          "reason": "无涨跌幅数据"}
    else:
        consec_premium = {"available": False, "reason": "无 2 板以上个股"}

    # ④ 梯队断层：今日 boards>=2 高度计数与缺档。
    consec = [int(r.get("limit_days") or 1) for r in zt_rows]
    consec2 = [b for b in consec if b >= 2]
    if consec:
        highest = max(consec2) if consec2 else max(consec)
        tiers_count: dict[int, int] = {}
        for b in consec2:
            tiers_count[b] = tiers_count.get(b, 0) + 1
        gaps = [b for b in range(2, highest) if b not in tiers_count]
        note = ("梯队连续" if not gaps else
                f"板位缺档 {'、'.join(f'{b}板' for b in gaps)} → 最高标下方断层")
        ladder_gap = {"highest": highest,
                      "tiers": {str(b): tiers_count[b] for b in sorted(tiers_count, reverse=True)},
                      "gaps": gaps, "continuous": not gaps, "note": note}
    else:
        ladder_gap = {"highest": None, "tiers": {}, "gaps": [],
                      "continuous": True, "note": "今日无涨停"}

    return {"date": trade_date, "prev_date": prev_date, "settled": True,
            "money_effect": money_effect, "promotion": promotion,
            "consec_premium": consec_premium, "ladder_gap": ladder_gap}


# ---------------------------------------------------------------------------
# 2. daily 六项读数
# ---------------------------------------------------------------------------

def build_daily(trade_date: str, prev_date: str | None,
                zt_rows: list[dict], zb_rows: list[dict],
                yzt_rows: list[dict], prev_zt_rows: list[dict]) -> dict:
    reasons: dict[str, str] = {}
    n_zt, n_zb = len(zt_rows), len(zb_rows)
    limit_up = n_zt
    highest_board = max((int(r.get("limit_days") or 1) for r in zt_rows), default=None)
    broken_rate = _r3(n_zb / (n_zb + n_zt)) if (n_zb or n_zt) else None

    rets = _rets(yzt_rows)
    money_effect = _r2(statistics.median(rets)) if rets else None
    deep_loss = sum(1 for x in rets if x <= -5)

    promotion_1to2 = None
    promo_base = promo_promoted = None
    if prev_zt_rows and zt_rows:
        zt_codes = {str(r.get("code") or "") for r in zt_rows}
        base = [r for r in prev_zt_rows if int(r.get("limit_days") or 1) == 1]
        promoted = sum(1 for r in base if str(r.get("code") or "") in zt_codes)
        promo_base, promo_promoted = len(base), promoted
        promotion_1to2 = _r3(promoted / len(base)) if base else None
    else:
        reasons["promotion"] = "昨日/今日涨停池缺一"
    if not rets:
        reasons["settled"] = "昨日涨停池无涨跌幅数据"

    return {
        "date": trade_date, "prev_date": prev_date, "settled": True,
        "readings": {
            "limit_up": limit_up,
            "highest_board": highest_board,
            "broken_rate": broken_rate,
            "money_effect": money_effect,
            "deep_loss": deep_loss,
            "promotion_1to2": promotion_1to2,
        },
        "sample": len(rets),
        "promotion_base": promo_base,
        "promotion_promoted": promo_promoted,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# 3. facts 打板事实（六张表）
# ---------------------------------------------------------------------------

_FEEDBACK_RESULT_ORDER = ["晋级涨停", "收红", "小跌", "跌超5%", "跌停"]
_TIMELINE_SLOTS = [(925, 935), (935, 1000), (1000, 1130), (1130, 1400), (1400, 1500)]
_TIMELINE_LABELS = ["09:25-09:35", "09:35-10:00", "10:00-11:30", "11:30-14:00", "14:00-15:00"]


def build_facts(trade_date: str, prev_date: str | None,
                zt_rows: list[dict], zb_rows: list[dict], dt_rows: list[dict],
                yzt_rows: list[dict], prev_zt_rows: list[dict]) -> dict:
    zt_codes = {str(r.get("code") or "") for r in zt_rows}

    # --- seal_quality 封板质量 ---
    broken_times = [int(r.get("break_times") or 0) for r in zt_rows]
    n_zt, n_zb = len(zt_rows), len(zb_rows)
    seal_quality = {
        "total": n_zt,
        "never_broken": sum(1 for b in broken_times if b == 0),
        "never_broken_rate": _r3(sum(1 for b in broken_times if b == 0) / n_zt) if n_zt else None,
        "opening_seconds": sum(1 for r in zt_rows if (_seal_minute(r.get("first_seal")) or 9999) <= 935),
        "late_seal": sum(1 for r in zt_rows if (_seal_minute(r.get("last_seal")) or 0) >= 1430),
        "reopened": sum(1 for b in broken_times if b >= 1),
        "avg_broken_times": _r2(sum(broken_times) / n_zt) if n_zt else None,
        "broken_pool": n_zb,
        "broken_rate": _r3(n_zb / (n_zb + n_zt)) if (n_zb or n_zt) else None,
        "ever_opened_rate": _r3(sum(1 for b in broken_times if b >= 1) / n_zt) if n_zt else None,
    }

    # --- loss_effect 亏钱效应 ---
    rets = _rets(yzt_rows)
    dn = [is_limit_down_row(r.get("pct"), r.get("code"), r.get("name"), trade_date)
          for r in yzt_rows]
    loss_effect = {
        "deep_loss_5_count": sum(1 for x in rets if x <= -5),
        "deep_loss_5_rate": _r3(sum(1 for x in rets if x <= -5) / len(rets)) if rets else None,
        "deep_loss_7_count": sum(1 for x in rets if x <= -7),
        "limit_down_count": sum(1 for x in dn if x is True),
        "worst": _r2(min(rets)) if rets else None,
        "market_limit_down": len(dt_rows),
    }

    # --- feedback 反馈矩阵（prev 日涨停股 × 今日结果） ---
    matrix: dict[str, dict] = {}
    details: list[dict] = []
    for r in yzt_rows:
        pb = int(r.get("y_limit_days") or 1)
        tier = "首板" if pb == 1 else f"{pb}板"
        ret = r.get("pct")
        code = str(r.get("code") or "")
        if code in zt_codes:
            result = "晋级涨停"
        elif is_limit_down_row(ret, code, r.get("name"), trade_date) is True:
            result = "跌停"
        elif ret is not None and float(ret) <= -5:
            result = "跌超5%"
        elif ret is not None and float(ret) > 0:
            result = "收红"
        else:
            result = "小跌"
        cell = matrix.setdefault(
            tier, {k: 0 for k in _FEEDBACK_RESULT_ORDER} | {"合计": 0, "晋级率": None})
        cell[result] += 1
        cell["合计"] += 1
        try:
            ret_v = _r2(float(ret)) if ret is not None else None
        except (TypeError, ValueError):
            ret_v = None
        details.append({"code": code, "name": r.get("name"),
                        "board": board_of(code, r.get("name")),
                        "prev_tier": tier, "ret": ret_v, "result": result,
                        "sector": r.get("industry")})
    for tier, cell in matrix.items():
        cell["晋级率"] = _r3(cell["晋级涨停"] / cell["合计"]) if cell["合计"] else None
    details.sort(key=lambda d: (d["ret"] is None, d["ret"] if d["ret"] is not None else 0))
    feedback = {"matrix": matrix, "details": details, "result_order": _FEEDBACK_RESULT_ORDER}

    # --- themes 题材结构（按东财行业归组；reason 版在 kind=themes） ---
    themes: dict[str, dict] = {}
    for r in zt_rows:
        key = str(r.get("industry") or "未分类")
        t = themes.setdefault(key, {
            "sector": key, "limit_up": 0, "first_boards": 0, "consec_boards": 0,
            "highest": 0, "broken": 0, "first_seal": None, "last_seal": None,
            "names": []})
        b = int(r.get("limit_days") or 1)
        t["limit_up"] += 1
        t["first_boards"] += 1 if b <= 1 else 0
        t["consec_boards"] += 1 if b >= 2 else 0
        t["highest"] = max(t["highest"], b)
        t["first_seal"] = min(t["first_seal"] or "999999", str(r.get("first_seal") or "999999"))
        t["last_seal"] = max(t["last_seal"] or "", str(r.get("last_seal") or ""))
        t["names"].append({"code": r.get("code"), "name": r.get("name"), "boards": b,
                           "first_seal": r.get("first_seal"),
                           "broken_times": int(r.get("break_times") or 0)})
    zb_by_industry: dict[str, int] = {}
    for r in zb_rows:
        key = str(r.get("industry") or "未分类")
        zb_by_industry[key] = zb_by_industry.get(key, 0) + 1
    for key, t in themes.items():
        t["broken"] = zb_by_industry.get(key, 0)
        t["broken_rate"] = _r3(t["broken"] / (t["broken"] + t["limit_up"])) \
            if (t["broken"] or t["limit_up"]) else None
        t["names"] = sorted(t["names"], key=lambda n: -n["boards"])[:6]
    theme_count = len(themes)
    concentration = _r3(
        max((t["limit_up"] for t in themes.values()), default=0) / n_zt) if n_zt else None
    timeline = []
    for (lo, hi), label in zip(_TIMELINE_SLOTS, _TIMELINE_LABELS):
        timeline.append({"slot": label, "count": sum(
            1 for r in zt_rows
            if (m := _seal_minute(r.get("first_seal"))) is not None and lo < m <= hi)})
    facts_themes = {"theme_count": theme_count, "concentration": concentration,
                    "timeline": timeline, "groups": themes}

    # --- events 关键事件账本 ---
    events: list[dict] = []
    if zt_rows:
        highest = max(int(r.get("limit_days") or 1) for r in zt_rows)
        for r in zt_rows:
            if int(r.get("limit_days") or 1) == highest:
                events.append({"tag": "最高标", "code": r.get("code"), "name": r.get("name"),
                               "boards": highest, "sector": r.get("industry"),
                               "first_seal": r.get("first_seal"), "note": f"今日最高 {highest} 板"})
        for r in sorted(zt_rows, key=lambda x: -int(x.get("break_times") or 0))[:3]:
            if int(r.get("break_times") or 0) >= 2:
                events.append({"tag": "反复开板", "code": r.get("code"), "name": r.get("name"),
                               "broken_times": int(r.get("break_times") or 0),
                               "sector": r.get("industry")})
        seen_industry: set[str] = set()
        firsts = []
        for r in sorted(zt_rows, key=lambda x: str(x.get("first_seal") or "999999")):
            industry = str(r.get("industry") or "")
            if industry and industry not in seen_industry:
                seen_industry.add(industry)
                firsts.append(r)
        for r in firsts[:4]:
            events.append({"tag": "题材首封", "code": r.get("code"), "name": r.get("name"),
                           "sector": r.get("industry"), "first_seal": r.get("first_seal")})
    for r in sorted(zb_rows, key=lambda x: -stat_boards(x.get("zt_stat"), 1))[:6]:
        pb = stat_boards(r.get("zt_stat"), 1)
        tag = "高位断板" if pb >= 3 else ("连板断板" if pb >= 2 else "炸板")
        events.append({"tag": tag, "code": r.get("code"), "name": r.get("name"),
                       "prev_boards": pb, "sector": r.get("industry")})
    yzt_boards = {str(r.get("code") or ""): int(r.get("y_limit_days") or 1) for r in yzt_rows}
    for r in sorted(dt_rows, key=lambda x: (-(yzt_boards.get(str(x.get("code") or ""), 0)),
                                            -int(x.get("dt_days") or 0)))[:5]:
        pb = yzt_boards.get(str(r.get("code") or ""), 0)
        events.append({"tag": "高标跌停" if pb >= 2 else "跌停", "code": r.get("code"),
                       "name": r.get("name"), "prev_boards": pb or None,
                       "consec_dt": int(r.get("dt_days") or 1), "sector": r.get("industry")})

    # --- by_board 分制度生态 ---
    by_board: dict[str, dict] = {}
    prev_by_board = _group_by_board(prev_zt_rows)
    zb_by_board = _group_by_board(zb_rows)
    dt_by_board = _group_by_board(dt_rows)
    zt_by_board = _group_by_board(zt_rows)
    for board in (set(zt_by_board) | set(zb_by_board) | set(dt_by_board) | set(prev_by_board)):
        g = zt_by_board.get(board, [])
        p = prev_by_board.get(board, [])
        p_codes = {str(r.get("code") or "") for r in p}
        promoted = sum(1 for r in g if str(r.get("code") or "") in p_codes)
        by_board[board] = {
            "limit_up": len(g),
            "highest": max((int(r.get("limit_days") or 1) for r in g), default=0),
            "prev_base": len(p),
            "promoted": promoted,
            "broken": len(zb_by_board.get(board, [])),
            "limit_down": len(dt_by_board.get(board, [])),
            "promotion_rate": _r3(promoted / len(p)) if p else None,
        }

    return {"date": trade_date, "prev_date": prev_date, "settled": True,
            "seal_quality": seal_quality, "loss_effect": loss_effect,
            "feedback": feedback, "themes": facts_themes,
            "events": events, "by_board": by_board,
            "prev_available": bool(prev_zt_rows)}


# ---------------------------------------------------------------------------
# 4. structure 每日结构
# ---------------------------------------------------------------------------

def build_structure(trade_date: str,
                    zt_rows: list[dict], zb_rows: list[dict],
                    dt_rows: list[dict], yzt_rows: list[dict]) -> dict:
    if not zt_rows:
        return {"date": trade_date, "settled": True, "available": False,
                "reason": "涨停池为空或未同步", "limit_up": 0}

    mix = {"20%": 0, "10%": 0, "北交所": 0}
    for r in zt_rows:
        code, name = r.get("code"), r.get("name")
        if board_of(code, name) == "北交所":
            mix["北交所"] += 1
        elif limit_pct(code, name, trade_date) >= 20:
            mix["20%"] += 1
        else:
            mix["10%"] += 1
    n = len(zt_rows)
    highest = max(int(r.get("limit_days") or 1) for r in zt_rows)
    tops = sorted((r for r in zt_rows if int(r.get("limit_days") or 1) == highest),
                  key=lambda r: (str(r.get("first_seal") or "999999"), str(r.get("code") or "")))
    return {
        "date": trade_date, "settled": True, "available": True,
        "limit_up": n,
        "mix": mix,
        "share_20cm": _r3(mix["20%"] / n),
        "share_10cm": _r3(mix["10%"] / n),
        "share_bj": _r3(mix["北交所"] / n),
        "highest_board": highest,
        "leader_total": len(tops),
        "leaders": [{"code": r.get("code"), "name": r.get("name"),
                     "boards": highest, "sector": r.get("industry"),
                     "first_seal": r.get("first_seal"),
                     "zt_stat": r.get("zt_stat")} for r in tops[:5]],
        "pool_counts": {"zt": len(zt_rows), "zb": len(zb_rows),
                        "dt": len(dt_rows), "yzt": len(yzt_rows)},
    }


# ---------------------------------------------------------------------------
# 5. ladder 昨日梯队
# ---------------------------------------------------------------------------

def build_ladder(quote_date: str, sample_date: str | None,
                 prev_zt_rows: list[dict]) -> dict:
    """quote_date = 盯的那一场（行情日）；名单来自 sample_date = 其前一交易日。"""
    if not prev_zt_rows:
        return {"quote_date": quote_date, "sample_date": sample_date,
                "available": False, "reason": "样本日涨停池为空或未同步（东财池只留约一个月）",
                "stocks": [], "total": 0}
    stocks = sorted(
        ({
            "code": str(r.get("code") or ""),
            "name": r.get("name"),
            "boards": int(r.get("limit_days") or 1),
            "label": board_label(r.get("zt_stat"), int(r.get("limit_days") or 1)),
            "sector": r.get("industry"),
            "first_seal": r.get("first_seal"),
            "broken_times": int(r.get("break_times") or 0),
        } for r in prev_zt_rows),
        key=lambda s: (-s["boards"], s["code"]))
    tiers: list[dict] = []
    for s in stocks:
        if tiers and tiers[-1]["boards"] == s["boards"]:
            tiers[-1]["count"] += 1
        else:
            tiers.append({"boards": s["boards"], "count": 1})
    return {"quote_date": quote_date, "sample_date": sample_date,
            "available": True, "stocks": stocks, "total": len(stocks),
            "highest": stocks[0]["boards"], "tiers": tiers}


# ---------------------------------------------------------------------------
# 6. settled 昨日涨停样本
# ---------------------------------------------------------------------------

def build_settled(trade_date: str, prev_date: str | None,
                  yzt_rows: list[dict]) -> dict:
    if not yzt_rows:
        return {"date": trade_date, "prev_date": prev_date, "settled": True,
                "available": False, "reason": "昨日涨停池无数据", "rows": []}
    rows = []
    n_ret = 0
    for r in yzt_rows:
        ret = r.get("pct")
        try:
            ret_v = _r2(float(ret)) if ret is not None else None
        except (TypeError, ValueError):
            ret_v = None
        if ret_v is not None:
            n_ret += 1
        rows.append({
            "code": str(r.get("code") or ""), "name": r.get("name"),
            "ret": ret_v,
            "prev_boards": int(r.get("y_limit_days") or 1),
            "seal_time": r.get("y_first_seal"),
            "sector": r.get("industry"),
            "limit_up": is_limit_up_row(
                r.get("price"), r.get("limit_price"), r.get("pct"),
                r.get("code"), r.get("name"), trade_date),
        })
    rows.sort(key=lambda x: -(x["prev_boards"] or 0))
    expected = len(rows)
    return {
        "date": trade_date, "prev_date": prev_date, "settled": True,
        "available": True, "rows": rows,
        "settled_cov": {
            "sample": n_ret, "expected_sample": expected,
            "coverage_rate": _r3(n_ret / expected) if expected else None,
            "partial": n_ret < expected,
        },
    }


# ---------------------------------------------------------------------------
# 7. cycle 情绪周期
# ---------------------------------------------------------------------------

def _minmax_norm(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def build_cycle(trade_date: str, window: list[tuple[str, list[dict], list[dict]]],
                requested_window: int) -> dict:
    """window = [(date, zt_rows, zb_rows)] 升序；缺池的日由调用方剔除或本函数丢弃。"""
    series_src = []
    for day, zt_rows, zb_rows in window:
        if not zt_rows:
            continue  # 涨停池空/缺 → 该日丢弃
        n_zt, n_zb = len(zt_rows), len(zb_rows)
        series_src.append({
            "date": day,
            "limit_up": n_zt,
            "highest_consec": max(int(r.get("limit_days") or 1) for r in zt_rows),
            "broken_rate": (n_zb / (n_zb + n_zt)) if (n_zb or n_zt) else None,
        })
    if len(series_src) < 3:
        return {"available": False, "reason": "可用交易日不足 3 天",
                "requested_window": requested_window, "window": len(series_src)}

    nz = _minmax_norm([float(s["limit_up"]) for s in series_src])
    nh = _minmax_norm([float(s["highest_consec"]) for s in series_src])
    br = [s["broken_rate"] for s in series_src]
    nb = _minmax_norm([1.0 - float(b) for b in br])
    series = []
    for i, s in enumerate(series_src):
        series.append({
            "date": s["date"], "limit_up": s["limit_up"],
            "highest_consec": s["highest_consec"],
            "broken_rate": _r3(s["broken_rate"]),
            "score": _r3((nz[i] + nh[i] + nb[i]) / 3),
        })
    scores = [s["score"] for s in series]
    trough_idx = scores.index(min(scores))
    trough_score, current_score = scores[trough_idx], scores[-1]
    top_score = max(scores)
    trend = "样本不足"
    if len(scores) >= 3:
        d1, d2, d3 = scores[-3], scores[-2], scores[-1]
        if d2 > d1 and d3 > d2:
            trend = "连续两日走强"
        elif d2 < d1 and d3 < d2:
            trend = "连续两日转弱"
        elif d3 > d2:
            trend = "今日走强"
        elif d3 < d2:
            trend = "今日走弱"
        else:
            trend = "基本走平"
    return {
        "available": True,
        "requested_window": requested_window,
        "window": len(series),
        "trough_date": series[trough_idx]["date"],
        "trough_score": trough_score,
        "current_date": series[-1]["date"],
        "current_score": current_score,
        "day_n": len(series) - 1 - trough_idx,
        "rising": current_score > trough_score,
        "trend": trend,
        "pctile": _r3((current_score - trough_score) / (top_score - trough_score))
        if top_score > trough_score else None,
        "series": series,
    }


# ---------------------------------------------------------------------------
# 8. live 此刻读数（盘中批计算）
# ---------------------------------------------------------------------------

def build_live(trade_date: str, phase: str, as_of: str,
               zt_rows: list[dict], zb_rows: list[dict], dt_rows: list[dict],
               yzt_rows: list[dict], prev_zt_rows: list[dict]) -> dict:
    if not zt_rows:
        return {"date": trade_date, "as_of": as_of, "phase": phase,
                "available": False, "reason": "今日涨停池无数据"}
    zt_codes = {str(r.get("code") or "") for r in zt_rows}
    prev_codes = {str(r.get("code") or "") for r in prev_zt_rows}
    prev_base1 = [c for r in prev_zt_rows
                  if int(r.get("limit_days") or 1) == 1 for c in [str(r.get("code") or "")]]
    promoted_all = sum(1 for c in prev_codes if c in zt_codes)
    promoted_1to2 = sum(1 for c in prev_base1 if c in zt_codes)
    rets = _rets(yzt_rows)
    n_zt, n_zb = len(zt_rows), len(zb_rows)
    return {
        "date": trade_date, "as_of": as_of, "phase": phase, "available": True,
        "limit_up": n_zt,
        "broken": n_zb or None,
        "limit_down": len(dt_rows) or None,
        "highest_board": max(int(r.get("limit_days") or 1) for r in zt_rows),
        "consec_count": sum(1 for r in zt_rows if int(r.get("limit_days") or 1) >= 2),
        "seal_rate": _r3(n_zt / (n_zt + n_zb)) if (n_zt or n_zb) else None,
        "promotion_all": {
            "base": len(prev_codes), "promoted": promoted_all,
            "rate": _r3(promoted_all / len(prev_codes)) if prev_codes else None},
        "promotion_1to2": {
            "base": len(prev_base1), "promoted": promoted_1to2,
            "rate": _r3(promoted_1to2 / len(prev_base1)) if prev_base1 else None},
        "money_effect": {
            "median": _r2(statistics.median(rets)) if rets else None,
            "sample": len(rets)},
        "deep_loss": sum(1 for x in rets if x <= -5),
    }


# ---------------------------------------------------------------------------
# 9-12. 题材家族（输入 = ths_limit_up.reason + 池表）
# ---------------------------------------------------------------------------

def clean_reason(reason: Any) -> list[str]:
    """拆 reason 标签：分隔符切分 → 滤空/泛属性词 → ≤4 个、总长 40。"""
    import re
    text = _norm_name(reason)
    if not text:
        return []
    tags = [t.strip() for t in re.split(r"[+＋、,，;；/]", text) if t.strip()]
    tags = [t for t in tags if not any(w in t for w in _GENERIC_REASON_WORDS)]
    out: list[str] = []
    total = 0
    for t in tags:
        if len(out) >= _MAX_REASON_TAGS or total + len(t) > _MAX_REASON_TOTAL_LEN:
            break
        out.append(t)
        total += len(t)
    return out


def _reason_by_code(ths_rows: list[dict]) -> dict[str, str]:
    return {str(r.get("code") or ""): str(r.get("reason") or "") for r in ths_rows}


def theme_map(zt_rows: list[dict], ths_rows: list[dict]) -> dict[str, list[dict]]:
    """题材 → 涨停行列表（一股多标签会进多个题材；无标签的行不进树）。"""
    reason_by_code = _reason_by_code(ths_rows)
    out: dict[str, list[dict]] = {}
    for r in zt_rows:
        for tag in clean_reason(reason_by_code.get(str(r.get("code") or ""), "")):
            out.setdefault(tag, []).append(r)
    return out


def theme_counts(zt_rows: list[dict], ths_rows: list[dict]) -> dict[str, int] | None:
    """题材 → 当日涨停数；两池皆空返回 None（轮动序列里的"缺日"）。"""
    if not zt_rows and not ths_rows:
        return None
    return {tag: len(rows) for tag, rows in theme_map(zt_rows, ths_rows).items()}


def build_themes(trade_date: str, zt_rows: list[dict],
                 ths_rows: list[dict]) -> dict:
    has_reason = any(str(r.get("reason") or "").strip() for r in ths_rows)
    if not zt_rows or not has_reason:
        # reason 整体缺失：不拿 industry 冒充题材（VA 语义）。
        return {"date": trade_date, "available": False, "theme_count": 0, "themes": {},
                "reason": "ths_limit_up.reason 缺失（同花顺涨停揭秘未同步）"}
    tree: dict[str, dict] = {}
    for tag, rows in theme_map(zt_rows, ths_rows).items():
        boards = [int(r.get("limit_days") or 1) for r in rows]
        names = sorted(
            ({"code": r.get("code"), "name": r.get("name"),
              "boards": int(r.get("limit_days") or 1),
              "first_seal": r.get("first_seal"),
              "broken_times": int(r.get("break_times") or 0)} for r in rows),
            key=lambda n: (-n["boards"], str(n["code"])))
        tree[tag] = {
            "limit_up": len(rows),
            "first_boards": sum(1 for b in boards if b <= 1),
            "consec_boards": sum(1 for b in boards if b >= 2),
            "highest": max(boards),
            "names": names[:10],
        }
    ordered = dict(sorted(tree.items(), key=lambda kv: (-kv[1]["limit_up"], kv[0])))
    return {"date": trade_date, "available": True, "theme_count": len(tree),
            "themes": ordered}


def build_firstboard(trade_date: str, zt_rows: list[dict],
                     ths_rows: list[dict]) -> dict:
    reason_by_code = _reason_by_code(ths_rows)
    rows = []
    missing_reason = 0
    for r in zt_rows:
        if int(r.get("limit_days") or 1) != 1:
            continue
        reason = clean_reason(reason_by_code.get(str(r.get("code") or ""), ""))
        if not reason:
            missing_reason += 1
        rows.append({
            "code": r.get("code"), "name": r.get("name"),
            "sector": r.get("industry"), "first_seal": r.get("first_seal"),
            "seal_fund": r.get("seal_fund"), "turnover": r.get("turnover"),
            "reason": reason or None,
        })
    rows.sort(key=lambda x: (str(x["first_seal"] or "999999"), str(x["code"] or "")))
    has_reason = any(reason_by_code.values())
    return {
        "date": trade_date, "available": bool(rows), "total": len(rows),
        "rows": rows,
        "reasons_available": has_reason,
        "partial": bool(missing_reason) or not has_reason,
        "missing_reason": missing_reason,
    }


def build_board_ladder(trade_date: str, zt_rows: list[dict], zb_rows: list[dict],
                       dt_rows: list[dict], prev_zt_rows: list[dict]) -> dict:
    zt_codes = {str(r.get("code") or "") for r in zt_rows}
    zb_codes = {str(r.get("code") or "") for r in zb_rows}
    dt_codes = {str(r.get("code") or "") for r in dt_rows}

    def _by_boards(rows: list[dict]) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        for r in rows:
            out.setdefault(int(r.get("limit_days") or 1), []).append(r)
        return out

    prev_groups = _by_boards(prev_zt_rows)
    today_groups = _by_boards(zt_rows)
    heights = sorted(set(prev_groups) | set(today_groups), reverse=True)
    if not heights:
        return {"date": trade_date, "available": False, "tiers": [],
                "reason": "今日/昨日涨停池均为空"}

    tiers = []
    for h in heights:
        today = sorted(today_groups.get(h, []),
                       key=lambda r: (str(r.get("first_seal") or "999999"), str(r.get("code") or "")))
        fates = []
        for r in sorted(prev_groups.get(h, []),
                        key=lambda r: str(r.get("code") or "")):
            code = str(r.get("code") or "")
            to = "zt" if code in zt_codes else (
                "zb" if code in zb_codes else ("dt" if code in dt_codes else "other"))
            fates.append({"code": r.get("code"), "name": r.get("name"), "to": to})
        tiers.append({
            "boards": h,
            "label": f"{h}板",
            "count": len(today),
            "stocks": [{
                "code": r.get("code"), "name": r.get("name"),
                "label": board_label(r.get("zt_stat"), h),
                "sector": r.get("industry"), "first_seal": r.get("first_seal"),
                "seal_fund": r.get("seal_fund"),
                "broken_times": int(r.get("break_times") or 0)} for r in today],
            "promoted": sum(1 for f in fates if f["to"] == "zt"),
            "fates": {k: sum(1 for f in fates if f["to"] == k)
                      for k in ("zt", "zb", "dt", "other")},
            "fate_detail": fates,
        })
    return {"date": trade_date, "available": True, "tiers": tiers,
            "highest": heights[0]}


def build_theme_rotation(trade_date: str, days: list[str],
                         groups: list[dict[str, int] | None],
                         requested_days: int = 5) -> dict:
    """days 与 groups 对齐；None = 该日池表缺数据（序列留 None 不当 0）。"""
    totals: dict[str, int] = {}
    for g in groups:
        for tag, n in (g or {}).items():
            totals[tag] = totals.get(tag, 0) + n
    themes = {}
    for tag in sorted(totals, key=lambda t: (-totals[t], t)):
        series = [g.get(tag) if g is not None else None for g in groups]
        non_null = [(i, v) for i, v in enumerate(series) if v is not None]
        peak_day = days[max(non_null, key=lambda iv: (iv[1], iv[0]))[0]] if non_null else None
        trend = None
        if len(non_null) >= 2:
            a, b = non_null[-2][1], non_null[-1][1]
            trend = "rising" if b > a else ("falling" if b < a else "flat")
        themes[tag] = {"series": series, "total": totals[tag],
                       "peak_day": peak_day, "trend": trend}
    return {"date": trade_date, "available": bool(themes),
            "requested_days": requested_days, "days": days, "themes": themes}


# ---------------------------------------------------------------------------
# 13-14. 本地派生（bars_daily / stock_daily_basic）
# ---------------------------------------------------------------------------

def build_turnover_top(trade_date: str, rows: list[dict]) -> dict:
    out = []
    for r in rows:
        amt = r.get("total_amt")
        try:
            amt_yi = round(float(amt) / 1e8, 2) if amt is not None else None
        except (TypeError, ValueError):
            amt_yi = None
        out.append({"code": r.get("code"), "name": r.get("name"),
                    "total_amt": amt, "total_amt_yi": amt_yi,
                    "close": r.get("close"), "rise_rate": r.get("rise_rate")})
    return {"date": trade_date, "available": bool(out), "rows": out}


def build_bigcaps(trade_date: str, rows: list[dict],
                  min_total_mv_wan: float = BIGCAP_TOTAL_MV_WAN) -> dict:
    out = []
    for r in rows:
        mv = r.get("total_mv")
        try:
            mv_yi = round(float(mv) / 1e4, 1) if mv is not None else None  # 万→亿
        except (TypeError, ValueError):
            mv_yi = None
        out.append({"code": r.get("code"), "name": r.get("name"),
                    "total_mv_wan": mv, "total_mv_yi": mv_yi,
                    "circ_mv": r.get("circ_mv"), "close": r.get("close"),
                    "turnover_rate": r.get("turnover_rate"), "pe": r.get("pe")})
    return {"date": trade_date, "threshold_mv_wan": min_total_mv_wan,
            "available": bool(out), "count": len(out), "rows": out}
