# -*- coding: utf-8 -*-
"""数字忠实度核心（移植自 vibe-astock arithmetic.ts + number_fidelity.ts）。

三层：

1. ``check_stated_arithmetic`` —— 文本里自己写出来的算式，就地重算。算出来的数字
   没法跟已知值比对（它是唯一"谁都没在看"的数字），只要把算式写出来了就重算，
   对不上就点名。只查算式自洽，不判断算式选得对不对。
2. ``claim_tokens`` —— 一行里需要证据支撑的数字主张（剥掉日期/年份/代码/序号/
   窗口标签/速率标签等非主张数字）。
3. ``number_bound`` / ``audit_numbers`` —— 数字与已知值池比对（含单位换算），
   四档分开报：bound（可溯源）/ derived（自洽算式）/ loose（没人在看，不等于错）/
   bad_math（唯一可断言"错了"的：算式自己写的、重算对不上）。

纯函数、无 IO。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# 基础归一
# ---------------------------------------------------------------------------


def _to_num(raw: str) -> "float | None":
    """千分位、全角减号、各种除号归一后的数值解析。"""
    s = raw.replace(",", "").replace("−", "-").replace("—", "-").replace("–", "-")
    if s.startswith("+"):
        s = s[1:]
    s = s.strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------------------
# 带单位的项
# ---------------------------------------------------------------------------

_MAG = {"万亿": 1e12, "亿": 1e8, "万": 1e4}

# 正号要允许：真实文本写 `= +0.2%`，不认正号整条算式识别不出来。
_NUM = r"[+\-−—–]?\d[\d,]*(?:\.\d+)?"
# 数字与运算符之间常夹单位：`444.64 亿 ÷ 453.90 亿 − 1`。只放行紧跟数字的少量单位字。
# 单位参与运算（不能只吃掉）：`2 亿 + 3 万 = 5 亿元` 按裸数重算会判成对的。
_UNIT = r"\s*(万亿|亿|万)?(%|[元股倍]{0,2})"
_RESULT_UNIT = r"\s*(万亿|亿|万)?\s*(%|[元股倍])?"


@dataclass
class _Term:
    v: float
    k: float          # 归一系数（亿=1e8、%=0.01）
    scaled: bool      # 写了数量级或 %
    dim: str          # 量纲（% / 元 / 股 / 倍，没写为空）
    mag: bool         # 写了数量级（% 不算）


def _term(raw: "str | None", mag: "str | None", suffix: "str | None") -> "_Term | None":
    v = _to_num(raw or "")
    if v is None:
        return None
    dim = "%" if suffix == "%" else (suffix or "")[:1]
    k = (_MAG[mag] if mag else 1) * (0.01 if suffix == "%" else 1)
    return _Term(v=v, k=k, scaled=bool(mag) or suffix == "%", dim=dim, mag=bool(mag))


def _pct_k(t: _Term) -> float:
    return 0.01 if t.dim == "%" else 1.0


def _same_dim(x: str, y: str) -> bool:
    """加减两边是不是同一种量。没写单位名的一边按同一种看；% 必须两边都写。"""
    return x == y or (x != "%" and y != "%" and (not x or not y))


def _unitless(t: _Term) -> bool:
    """没写数量级也没写单位名的数（裸数或百分比）：结果写了数量级时才可能是省略写法。"""
    return not t.mag and (not t.dim or t.dim == "%")


def _own_unit(t: _Term) -> bool:
    """自己写清了单位的数：写了数量级或单位名（百分比不算单位名）。"""
    return t.mag or (bool(t.dim) and t.dim != "%")


def _either_reading(stated: float, omitted: float, literal: float) -> float:
    """结果写了数量级时的两种读法：运算数按结果数量级读（省略写法），或按字面读、
    结果换了单位（`5 × 2000 = 1 万`）。取数量级离写出来的结果更近的那种。"""
    def off(x: float) -> float:
        if x == 0 or stated == 0:
            return math.inf
        return abs(math.log10(abs(x / stated)))
    return literal if off(literal) < off(omitted) else omitted


_MINUS = r"[-−—–]"
_MUL = r"[*×]"
_DIV = r"[/÷]"
EQ_CHARS = "=＝≈"
_EQ = f"[{EQ_CHARS}]"
# 运算符与数字之间常夹一小段标签（`÷ 甲项 910.94 亿元`）：上限 8 字、不含数字/运算符/等号。
_LABEL = r"(?:\s*[^\d=＝≈+\-−—–*×/÷()（）,，;；]{0,8})?"


def _binary_result(op: str, a: _Term, b: _Term, r: _Term, r_explicit: bool, r_pct: bool) -> "float | None":
    """两数运算后的结果，换算回结果写出来的单位；说不清时 None（不认这条算式）。"""
    if op == "+" or re.fullmatch(_MINUS, op):
        return _sum_result([(a, 1), (b, 1 if op == "+" else -1)], r, r_explicit, r_pct)
    is_div = re.fullmatch(_DIV, op) is not None
    # 数量级只写在结果上是省略写法（`100 ÷ 8 = 12.5 亿`）：运算数按结果数量级读
    if r.mag and _unitless(a) and _unitless(b):
        if is_div:
            if b.v == 0:
                return None
            raw = (a.v * a.k) / (b.v * b.k)
        else:
            raw = a.v * a.k * b.v * b.k
        return _either_reading(r.v, raw / _pct_k(r), raw / r.k)
    if is_div:
        if b.v == 0:
            return None
        if not r_explicit:
            return (a.v * a.k) / (b.v * b.k) if a.scaled == b.scaled else None
        return (a.v * a.k) / (b.v * b.k) / r.k
    legacy_pct = r_pct and not r.mag and a.k == 1 and b.k == 1 and not a.dim and not b.dim
    if not r_explicit:
        return a.v * b.v if a.k == 1 and b.k == 1 else None
    if legacy_pct:
        return a.v * b.v
    return (a.v * a.k * b.v * b.k) / r.k


def _sum_result(terms: "list[tuple[_Term, int]]", r: _Term, r_explicit: bool, r_pct: bool) -> "float | None":
    """加减（两项或多项）的结果；量纲不同/说不清时 None。"""
    op_dim = next((t.dim for t, _ in terms if t.dim), "")
    if not all(_same_dim(t.dim, op_dim) for t, _ in terms):
        return None

    def total(f: Callable[[_Term], float]) -> float:
        return sum(sign * f(t) for t, sign in terms)

    if r.mag and all(_unitless(t) for t, _ in terms):
        if op_dim and not _same_dim(op_dim, r.dim):
            return None
        raw = total(lambda t: t.v * t.k)
        return _either_reading(r.v, raw / _pct_k(r), raw / r.k)
    if r.mag and not all(_own_unit(t) for t, _ in terms):
        return None
    if not r_explicit:
        return total(lambda t: t.v) if all(t.k == terms[0][0].k for t, _ in terms) else None
    if r_pct and not r.mag and all(t.k == 1 and not t.dim for t, _ in terms):
        return total(lambda t: t.v)
    if r.dim and op_dim and not _same_dim(op_dim, r.dim):
        return None
    return total(lambda t: t.v * t.k) / r.k


# 尾巴判定：这条匹配只是更长算式的尾巴（前面紧挨「数 运算符」）时不单独认。
_NUM_END = r"\d(?:[\d,]*\d)?(?:\.\d+)?\s*(?:万亿|亿|万)?(?:%|[元股倍]{0,2})"


def _is_tail(line: str, m: "re.Match[str]") -> bool:
    before = line[: m.start()].rstrip()
    if re.search(rf"{_NUM_END}\s*(?:{_MINUS}|\+|{_MUL}|{_DIV})$", before):
        return True
    return bool(re.match(r"^[+\-−—–]", m.group(0))) and bool(re.search(rf"{_NUM_END}$", before))


@dataclass
class StatedCalc:
    raw: str          # 原文片段
    stated: float     # 文本自己给出的结果
    recomputed: float  # 重算出来的结果
    percent: bool
    ok: bool


def _close_enough(stated: float, recomputed: float, approx_tol: float = 0.0) -> bool:
    """允许的误差：按结果量级给宽度（容下四舍五入），再宽会放过真错。"""
    tol = max(abs(recomputed) * 5e-3, 0.011, approx_tol)
    return abs(stated - recomputed) <= tol


def _approx_tolerance(stated_raw: str) -> float:
    """`≈` 后面的数只承诺写出来的那几位：容差给到最后一位有效数字的半格，
    封顶结果的 5%（不低于个位半格 0.5）。"""
    s = re.sub(r"[,\s]", "", stated_raw)
    s = re.sub(r"^[-+−]", "", s)
    m = re.search(r"\.(\d+)$", s)
    if m:
        return 0.5 * 10 ** -len(m.group(1))
    if re.fullmatch(r"0+", s):
        return 0.5
    zeros = len(re.search(r"0*$", s).group(0))
    half = 0.5 * 10 ** zeros
    return min(half, max(abs(_to_num(stated_raw) or 0) * 0.05, 0.5))


_EV_CALC_REF_RE = re.compile(
    r"\[(?:ev|calc)-[0-9a-zA-Z]+(?:\s*[,;]\s*(?:ev|calc)-[0-9a-zA-Z]+)*\]")
_PERIOD_TAG_RE = re.compile(r"\b\d{4}\s*(?:[HhQq][1-4]|FY|fy)\b")
_YEAR_CN_RE = re.compile(r"\b\d{4}\s*年度?")
_DASH_RE = re.compile(r"——")  # 中文破折号是标点不是负号


def check_stated_arithmetic(raw_line: str) -> list[StatedCalc]:
    """找出一行里写出来的算式并重算。四种形状：
    ``A ÷ B − 1 = R%`` · ``A − B = R`` · ``A + B = R`` · ``A × B = R``（含多项加减链）。"""
    out: list[StatedCalc] = []
    # 先剥标注（证据引用/期间标签/年份标签）再匹配，否则要求的形状一条都识别不出来
    line = _EV_CALC_REF_RE.sub(" ", raw_line)
    line = _PERIOD_TAG_RE.sub(" ", line)
    line = _YEAR_CN_RE.sub(" ", line)
    line = _DASH_RE.sub(" ", line)

    def push(raw: str, stated_raw: str, recomputed: float, percent: bool) -> None:
        st = _to_num(stated_raw)
        if st is None or not math.isfinite(recomputed):
            return
        approx_tol = _approx_tolerance(stated_raw) if "≈" in raw else 0.0
        out.append(StatedCalc(raw=raw.strip(), stated=st, recomputed=recomputed,
                              percent=percent, ok=_close_enough(st, recomputed, approx_tol)))

    # A ÷ B − 1 = R（同比；R 可带 %，带 % 时重算值 ×100 由 r.k 完成）
    ratio = re.compile(
        rf"({_NUM}){_UNIT}\s*{_DIV}{_LABEL}\s*({_NUM}){_UNIT}\s*{_MINUS}\s*1\s*{_EQ}{_LABEL}\s*({_NUM}){_RESULT_UNIT}")
    for m in ratio.finditer(line):
        if _is_tail(line, m):
            continue
        a = _term(m.group(1), m.group(2), m.group(3))
        b = _term(m.group(4), m.group(5), m.group(6))
        r = _term(m.group(7), m.group(8), m.group(9))
        if not a or not b or not r or b.v == 0:
            continue
        push(m.group(0), m.group(7), ((a.v * a.k) / (b.v * b.k) - 1) / r.k, m.group(9) == "%")

    # 多项加减链：整条拆开重算，两数式不再从里面挑尾巴
    chain_find = re.compile(
        rf"{_NUM}{_UNIT}(?:\s*(?:{_MINUS}|\+){_LABEL}\s*\d[\d,]*(?:\.\d+)?{_UNIT}){{2,}}"
        rf"\s*{_EQ}{_LABEL}\s*{_NUM}{_RESULT_UNIT}")
    chain = re.compile(
        rf"^({_NUM}{_UNIT}(?:\s*(?:{_MINUS}|\+){_LABEL}\s*\d[\d,]*(?:\.\d+)?{_UNIT}){{2,}})"
        rf"\s*{_EQ}{_LABEL}\s*({_NUM}){_RESULT_UNIT}$")
    covered: list[tuple[int, int]] = []
    for m in chain_find.finditer(line):
        if _is_tail(line, m):
            continue
        c = chain.fullmatch(m.group(0))
        if not c:
            continue
        term_re = re.compile(
            rf"(^|{_MINUS}|\+){_LABEL}\s*(\d[\d,]*(?:\.\d+)?){_UNIT}")
        terms: list[tuple[_Term, int]] = []
        for t in term_re.finditer(c.group(1)):
            v = _term(t.group(2), t.group(3), t.group(4))
            if v:
                sign = -1 if (t.group(1) and t.group(1) != "+") else 1
                terms.append((v, sign))
        # 拆出来的项要正好拼回整条左边，拼不回（中间混了乘除）就不认
        if len(terms) < 3 or term_re.sub("", c.group(1)).strip() != "":
            continue
        r_num, r_mag, r_suffix = c.groups()[-3:]
        stated = _term(r_num, r_mag, r_suffix)
        if not stated:
            continue
        covered.append((m.start(), m.end()))
        r_val = _sum_result(terms, stated, r_explicit=bool(r_mag or r_suffix), r_pct=r_suffix == "%")
        if r_val is None:
            continue
        push(m.group(0), r_num, r_val, r_suffix == "%")

    # A − B = R / A + B = R / A × B = R / A ÷ B = R
    binary = re.compile(
        rf"({_NUM}){_UNIT}\s*({_MINUS}|\+|{_MUL}|{_DIV}){_LABEL}\s*({_NUM}){_UNIT}"
        rf"\s*{_EQ}{_LABEL}\s*({_NUM}){_RESULT_UNIT}")
    for m in binary.finditer(line):
        if _is_tail(line, m) or any(s <= m.start() < e for s, e in covered):
            continue
        a = _term(m.group(1), m.group(2), m.group(3))
        op = m.group(4)
        b = _term(m.group(5), m.group(6), m.group(7))
        stated = _term(m.group(8), m.group(9), m.group(10))
        if not a or not b or not stated:
            continue
        # `A ÷ B − 1 = R` 已被 ratio 吃掉；这里再匹到的 `− 1 =` 会重复报，跳过
        if re.fullmatch(_MINUS, op) and b.v == 1 and re.search(_DIV, line):
            continue
        pct = m.group(10) == "%"
        r_val = _binary_result(op, a, b, stated, r_explicit=bool(m.group(9) or m.group(10)), r_pct=pct)
        if r_val is None:
            continue
        push(m.group(0), m.group(8), r_val, pct)
    return out


# ---------------------------------------------------------------------------
# 数字主张（claim tokens）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimLexicon:
    """领域词表（实例级依赖，A 股默认在 A_STOCK_LEXICON）。"""
    money_before: "re.Pattern[str]"           # 数值之前的金额语境（.search 用）
    money_after: "re.Pattern[str]"            # 数值之后的金额语境
    category_label_context: "re.Pattern[str]"  # 类别标签语境（1.6T/800G 是产品名）
    subject_code_patterns: tuple               # 主体编号形态（.sub 用）
    window_label_pattern: "re.Pattern[str]"   # 时间窗口标签（.sub 用）
    subject_code_is_six_digits: bool = True
    label_patterns: tuple = ()


A_STOCK_LEXICON = ClaimLexicon(
    money_before=re.compile(r"[$￥¥]|\b(?:资金|成交|市值|营收|利润|净利|金额)\s*[:：]?\s*$"),
    money_after=re.compile(r"^\s*(?:元|美元|港币|万元|亿元)"),
    category_label_context=re.compile(r"(?:光模块|速率|带宽|产品|型号|制程|算力|接口)\s*[:：]?\s*$|^\s*(?:系列|处理器|卡|模块)"),
    subject_code_patterns=(
        re.compile(r"(?<![\d.])\d{6}(?:\.(?:SZ|SH|BJ|sz|sh|bj))?(?![\d.])"),
    ),
    window_label_pattern=re.compile(r"(?<![\d.])(?:近|过去)\s*\d+\s*(?:年|月|日|天|周|个交易日|个星期)"),
)

_SPEED_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s?[TG](?:bps|b)?(?![A-Za-z0-9])")


def _strip_speed_labels(s: str, lex: ClaimLexicon) -> str:
    """类别标签（1.6T / 800G）不是数字主张——只在"有类别语境、无金额语境"时剥。"""
    def _sub(m: "re.Match[str]") -> str:
        before = s[max(0, m.start() - 12): m.start()]
        after = s[m.end(): m.end() + 12]
        if lex.money_before.search(before) or lex.money_after.search(after):
            return m.group(0)
        if lex.category_label_context.search(before) or lex.category_label_context.search(after):
            return " " * len(m.group(0))
        return m.group(0)
    return _SPEED_RE.sub(_sub, s)


def _mask(m: "re.Match[str]") -> str:
    # 等长空白遮掉，让 token 的 index 始终对应原始行
    return " " * len(m.group(0))


_DT_RE = re.compile(r"\d{4}-\d{2}-\d{2}[\sT]{0,3}\d{1,2}:\d{2}(?::\d{2})?")
_REF_TAG_RE = re.compile(r"\[资料:[^\]\n]*\]")
_DOTTED_DATE_RE = re.compile(r"(?<![\d.])(?:19|20)\d{2}\.\d{1,2}\.\d{1,2}(?![\d.])")
_URL_RE = re.compile(r"https?://[^\s)\]]+")
_HTTP_CODE_RE = re.compile(r"(?:HTTP|状态码|status)\s?[1-5]\d{2}(?!\d)", re.IGNORECASE)
_BULLETIN_NO_RE = re.compile(r"(?<![\d.])(?:19|20)\d{2}-\d{3,6}(?![\d.-])")
_DOMAIN_RE = re.compile(
    r"(?<![\w.])[\w-]+(?:\.[\w-]+)*\.(?:com|cn|net|org|io|co|hk|tw|jp|kr|de|uk|info|biz|tv|me|ai|app)(?:\.[a-z]{2})?(?![\w.])",
    re.IGNORECASE)
_ID_RE = re.compile(r"(?:ev-[0-9a-f]{6,}|calc-[0-9a-f]{16})(?![0-9A-Za-z_])")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_QUARTER_RE = re.compile(r"\d{4}Q[1-4]|\d{4}H[12]")
_FY_RE = re.compile(r"FY\s?\d{4}")
_BARE_YEAR_RE = re.compile(r"(?<![\d.])(?:19|20)\d{2}(?![\d.])\s*年?")
_ALPHA_CODE_RE = re.compile(r"(?<![\d.])[A-Za-z]\d+(?![\d.])")
_ORDINAL_RE = re.compile(
    r"第\s*\d+\s*[次条行名]|\d+\s*[次条行个家名项]\b|×\s*\d+|\d+\s*季度?|Q\d|(?<![\d.])\d+(?:\.\d+)?x\b",
    re.IGNORECASE)
_NUM_TOKEN_RE = re.compile(
    r"-?\d{1,3}(?:,\d{3})+(?![\d,])(?:\.\d+)?(?:e[+-]?\d+)?|-?\d+\.?\d*(?:e[+-]?\d+)?", re.IGNORECASE)
_SMALLINT_UNIT_RE = re.compile(r"^\s*(%|倍|元|亿|万|x|X|pp|百分点|期)")
_UNIT_ATTACH_RE = re.compile(r"^\s*(%|倍|元|亿|万|百分点|年|期)")


def claim_tokens(line: str, symbol: "str | None" = None,
                 lex: ClaimLexicon = A_STOCK_LEXICON) -> list[dict]:
    """一行里需要证据支撑的数字主张（已剥日期/年份/代码/序号/窗口标签等非主张）。"""
    s = _DT_RE.sub(_mask, line)
    s = _REF_TAG_RE.sub(_mask, s)
    s = _DOTTED_DATE_RE.sub(_mask, s)
    s = _URL_RE.sub(_mask, s)
    s = _HTTP_CODE_RE.sub(_mask, s)
    s = _BULLETIN_NO_RE.sub(_mask, s)
    s = _DOMAIN_RE.sub(_mask, s)
    s = _strip_speed_labels(s, lex)
    s = _ID_RE.sub(_mask, s)
    s = _DATE_RE.sub(_mask, s)
    s = _QUARTER_RE.sub(_mask, s)
    s = _FY_RE.sub(_mask, s)
    s = _BARE_YEAR_RE.sub(_mask, s)
    for re_ in lex.subject_code_patterns:
        s = re_.sub(_mask, s)
    s = _ALPHA_CODE_RE.sub(_mask, s)
    s = _ORDINAL_RE.sub(_mask, s)
    s = lex.window_label_pattern.sub(_mask, s)
    for re_ in lex.label_patterns:
        s = re_.sub(_mask, s)
    if lex.subject_code_is_six_digits and symbol and re.fullmatch(r"\d{6}", symbol or ""):
        s = re.sub(rf"(?<![\d.]){symbol}(?![\d.])", _mask, s)

    out: list[dict] = []
    for m in _NUM_TOKEN_RE.finditer(s):
        raw = m.group(0)
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        if not math.isfinite(n):
            continue
        after = s[m.end(): m.end() + 3]
        # ≤20 的纯整数小计数（"近 5 年"/"第 2 批"）不算数字主张；带小数点的是实数必须绑定
        if (float(n).is_integer() and abs(n) <= 20 and "e" not in raw.lower()
                and not re.search(r"\.\d", raw) and not _SMALLINT_UNIT_RE.match(after)):
            continue
        unit_m = _UNIT_ATTACH_RE.match(after)
        raw_ext = raw + (unit_m.group(0).strip() if unit_m else "")
        out.append({"n": n, "raw": raw_ext, "index": m.start()})
    return out


# ---------------------------------------------------------------------------
# 已知值池比对与四档审计
# ---------------------------------------------------------------------------

SCALES = [1, 1e4, 1e8, 100, 0.01, 1e-4, 1e-8]


def number_bound(token: float, pool: "Iterable[float]", rel_tol: float = 2e-3) -> bool:
    """token 是否对得上已知值池中某个数（含单位换算与四舍五入到分）。"""
    for v in pool:
        for s in SCALES:
            w = v * s
            if not math.isfinite(w):
                continue
            tol = max(abs(token) * rel_tol, rel_tol * 2.5)
            if abs(w - token) <= tol or abs(round(w * 100) / 100 - token) <= tol:
                return True
    return False


@dataclass
class LooseNumber:
    line: str
    value: float
    raw: str


@dataclass
class NumberAudit:
    total: int = 0
    bound: int = 0
    derived: int = 0
    loose: list = None          # list[LooseNumber]
    bad_math: list = None       # list[StatedCalc]

    def __post_init__(self):
        if self.loose is None:
            self.loose = []
        if self.bad_math is None:
            self.bad_math = []


def audit_numbers(
    text: str,
    known: "list[float]",
    claims: "Callable[[str], list[dict]] | None" = None,
    bound: "Callable[[float, list[float]], bool] | None" = None,
) -> NumberAudit:
    """审一段文本里的数字，四档分开报（bound/derived/loose/bad_math）。只标不改。"""
    if claims is None:
        claims = lambda line: claim_tokens(line)  # noqa: E731
    if bound is None:
        bound = number_bound
    res = NumberAudit()
    for line in re.split(r"\r?\n", text):
        if not line.strip():
            continue
        calcs = check_stated_arithmetic(line)
        res.bad_math.extend(c for c in calcs if not c.ok)
        in_calc = _derived_values(line)
        for t in claims(line):
            res.total += 1
            if bound(t["n"], known):
                res.bound += 1
            elif t["n"] in in_calc:
                res.derived += 1
            else:
                res.loose.append(LooseNumber(line=line.strip()[:160], value=t["n"], raw=t["raw"]))
    return res


# ---------------------------------------------------------------------------
# 遮蔽（M3：audit 只标不改 → 无出处数字替换为占位符）
# ---------------------------------------------------------------------------


def _derived_values(line: str) -> "set[float]":
    """自洽算式里出现过的数（含结果）——有交代，不算 loose。"""
    out: set[float] = set()
    for c in check_stated_arithmetic(line):
        if not c.ok:
            continue
        out.add(c.stated)
        for m in re.finditer(_NUM, c.raw):
            v = _to_num(m.group(0))
            if v is not None:
                out.add(v)
    return out


def numeric_leaves(obj: Any) -> "list[float]":
    """递归收集数值叶（bool 除外）——证据/计算记录构建已知值池用。"""
    if obj is None or isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)] if math.isfinite(float(obj)) else []
    if isinstance(obj, dict):
        out: list[float] = []
        for v in obj.values():
            out.extend(numeric_leaves(v))
        return out
    if isinstance(obj, (list, tuple)):
        out = []
        for v in obj:
            out.extend(numeric_leaves(v))
        return out
    return []


def mask_uncited(text: str, known: "list[float]",
                 mask: str = "〔未核实〕") -> "tuple[str, int]":
    """把无出处数字主张（loose 档）连紧邻单位替换为 mask。

    bound（对得上已知值池，含单位换算）与 derived（自洽算式里的数）不遮；
    bad_math 由审计另报，这里不处理。claim_tokens 的 index 与原行等长对齐
    （非主张 token 被等长空白遮掉），所以替换位点直接落在原文上。
    返回（遮蔽文, 遮蔽数）。
    """
    out_lines: list[str] = []
    count = 0
    for line in re.split(r"\r?\n", text):
        if not line.strip():
            out_lines.append(line)
            continue
        in_calc = _derived_values(line)
        spans = [(t["index"], t["index"] + len(t["raw"]))
                 for t in claim_tokens(line)
                 if not number_bound(t["n"], known) and t["n"] not in in_calc]
        if not spans:
            out_lines.append(line)
            continue
        buf: list[str] = []
        last = 0
        for start, end in spans:
            buf.append(line[last:start])
            buf.append(mask)
            last = end
            count += 1
        buf.append(line[last:])
        out_lines.append("".join(buf))
    return "\n".join(out_lines), count
