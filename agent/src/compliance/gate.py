"""产物级合规 gate（确定性后处理），移植自 vibe-astock orchestrator/src/gate.ts。

输入报告文本，输出命中清单；命中产出红线（投资动作建议类句子）即拒绝交付。
三重检查对抗规避：

1. ``canonical_for_gate`` 规范形：NFKC、剥不可见字符、繁→简、汉字之间的空白/点线
   分隔符忽略——插空格、插零宽字符、写成繁体，都命中同一个词；
2. ``markdown_visible`` 渲染后可见文字：链接/图片只留显示文字、剥反引号与 HTML
   标签、解字符实体与反斜杠转义——禁词被链接拆成 ``前[后](url)`` 时原文没有连续
   禁词、页面显示却是连起来的词，所以原文和渲染后两样都查；
3. 段落级拼接：同一段里换行渲染后只是一个空格，链接也能跨行写——按行移除后剩余
   的样子把未命中行连起来再查一遍。

只有整行精确等于固定免责声明的行才豁免（防"不构成建议，但建议……"半句翻转）。
纯函数、无 IO。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .gate_rules import EXEMPT_LINES, PATTERNS, PROBE_LINE, REGEXPS

# ---------------------------------------------------------------------------
# 规范形
# ---------------------------------------------------------------------------

# 简→繁（只覆盖红线词表用到的、繁简不同的字）
TRAD_CHARS: dict[str, str] = {
    "仓": "倉", "减": "減", "满": "滿", "议": "議", "买": "買", "卖": "賣",
    "评": "評", "级": "級", "损": "損", "标": "標", "价": "價", "荐": "薦",
}
_TRAD2SIMP: dict[str, str] = {t: s for s, t in TRAD_CHARS.items()}

# 汉字之间可忽略的分隔符（与 VA textsafe.py CJK_SEP_CHARS 逐字一致）
CJK_SEP_CHARS = " \t\r\n\u3000\u00b7\u2022\u30fb_*~|/\\+.\u2010\u2011\u2012\u2013\u2014\u2015-"
_CJK_CLASS = "\u3400-\u9fff\uf900-\ufaff"
_CJK_SEP_RE = re.compile(
    f"(?<=[{_CJK_CLASS}])[{re.escape(CJK_SEP_CHARS)}]+(?=[{_CJK_CLASS}])"
)

# 零宽字符是 Cf，蒙文/变体选择符是 Mn——都在下面 category 集合里；显式列五个是保险。
_INVISIBLE_EXTRA = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
_INVISIBLE_CATS = {"Cc", "Cf", "Mn", "Me"}


def canonical_for_gate(text: str) -> str:
    """gate 匹配用规范形（NFKC / 剥不可见 / 繁→简 / 汉字间分隔符剥除）。"""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(ch for ch in t
                if ch not in _INVISIBLE_EXTRA and unicodedata.category(ch) not in _INVISIBLE_CATS)
    t = "".join(_TRAD2SIMP.get(ch, ch) for ch in t)
    return _CJK_SEP_RE.sub("", t)


# ---------------------------------------------------------------------------
# 渲染后可见文字
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"!?\[([^[\]]*)\](?:\([^()]*\)|\[[^[\]]*\])")
_REF_USE_RE = re.compile(r"!?\[([^[\]]+)\](?!:)")
_REF_DEF_RE = re.compile(r"^ {0,3}(?:>\s*)*\[([^[\]]+)\]:", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
_NUM_ENTITY_RE = re.compile(r"&#(?:x([0-9a-fA-F]{1,6})|([0-9]{1,7}));")
_NAMED_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|nbsp);", re.IGNORECASE)
_ESCAPE_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
_NAMED_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}


def _ref_key(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).lower()


def reference_labels(report: str) -> set[str]:
    """全文里定义过的引用标签（``[仓]: https://…`` 这种行）；逐行检查看不到别的行。"""
    return {_ref_key(m.group(1)) for m in _REF_DEF_RE.finditer(report)}


def markdown_visible(line: str, refs: "set[str] | frozenset[str]" = frozenset()) -> str:
    """一行 Markdown 渲染后看得到的文字（只用于匹配）。"""
    t = line
    for _ in range(4):  # 链接套图片这类嵌套：由内往外逐层剥
        nxt = _LINK_RE.sub(r"\1", t)
        if refs:

            def _ref_sub(m: re.Match[str]) -> str:
                return m.group(1) if _ref_key(m.group(1)) in refs else m.group(0)

            nxt = _REF_USE_RE.sub(_ref_sub, nxt)
        if nxt == t:
            break
        t = nxt
    t = re.sub(r"`+", "", t)
    t = _HTML_TAG_RE.sub("", t)

    def _num_entity(m: re.Match[str]) -> str:
        hex_v, dec_v = m.group(1), m.group(2)
        try:
            cp = int(hex_v, 16) if hex_v else int(dec_v)
        except (TypeError, ValueError):
            return m.group(0)
        return chr(cp) if 0 < cp <= 0x10FFFF else m.group(0)

    t = _NUM_ENTITY_RE.sub(_num_entity, t)
    t = _NAMED_ENTITY_RE.sub(lambda m: _NAMED_ENTITIES[m.group(1).lower()], t)
    return _ESCAPE_RE.sub(r"\1", t)


# ---------------------------------------------------------------------------
# 主判官
# ---------------------------------------------------------------------------

@dataclass
class GateHit:
    line: int          # 1 起
    pattern: str       # 命中的子串或规则名
    text: str          # 命中行前 160 字


@dataclass
class GateResult:
    hits: list[GateHit] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hits

    def patterns(self) -> list[str]:
        return sorted({h.pattern for h in self.hits})


# 只剥真正的 Markdown 前缀（符号后必须有空白）；`>18%` 是"大于"不是引用块；
# `>` 只在后面是空白或另一个 `>`（嵌套引用 `>>`）时才算引用符。
_MD_PREFIX_RE = re.compile(r"^(?:(?:[-*+]|\d+[.)])\s+|>(?=[>\s])\s*)")


def _strip_md_prefix(line: str) -> str:
    while True:
        nxt = _MD_PREFIX_RE.sub("", line, count=1).strip()
        if nxt == line:
            return line
        line = nxt


def _check_patterns_and_regexps(
    canon: str, shown: str,
    patterns: list[str], regexps: list[tuple[str, "re.Pattern[str]"]],
) -> list[str]:
    found = [p for p in patterns if p in canon or p in shown]
    found += [name for name, re_ in regexps if re_.search(canon) or re_.search(shown)]
    return found


def compliance_gate(
    report: str,
    *,
    patterns: "list[str] | None" = None,
    exempt_lines: "list[str] | None" = None,
    regexps: "list[tuple[str, re.Pattern[str]]] | None" = None,
) -> GateResult:
    """对报告全文跑三重检查；返回命中清单（ok = 无命中）。"""
    patterns = PATTERNS if patterns is None else patterns
    exempt_lines = EXEMPT_LINES if exempt_lines is None else exempt_lines
    regexps = REGEXPS if regexps is None else regexps

    hits: list[GateHit] = []
    exempt = {canonical_for_gate(l.strip()) for l in exempt_lines}
    refs = reference_labels(report)
    raws = re.split(r"\r?\n", report)
    stripped: list[str] = [""] * len(raws)  # 豁免/空行记空串，段落检查时当分隔

    for i, raw in enumerate(raws):
        line = _strip_md_prefix(raw.strip())
        if not line:
            continue
        canon = canonical_for_gate(line)
        shown = canonical_for_gate(markdown_visible(line, refs))  # 页面上显示出来的那一行
        if canon in exempt or shown in exempt:
            continue
        stripped[i] = line
        for p in _check_patterns_and_regexps(canon, shown, patterns, regexps):
            hits.append(GateHit(i + 1, p, line[:160]))

    # 再按段落查一遍：跨行拼出来的词逐行查不出来。查的是"按行移除之后剩下的样子"
    # ——已命中的行当分隔，只拼相邻的、还没命中的行。拼出来命中的，run 里每行都记。
    line_hit = {h.line - 1 for h in hits}
    for block in _paragraphs(raws, stripped):
        runs: list[list[int]] = []
        run: list[int] = []
        for i in block:
            if i in line_hit:
                if run:
                    runs.append(run)
                run = []
            else:
                run.append(i)
        if run:
            runs.append(run)
        for r in runs:
            if len(r) < 2:  # 单独一行逐行已经查过
                continue
            joined = "\n".join(stripped[i] for i in r)
            canon = canonical_for_gate(joined)
            shown = canonical_for_gate(markdown_visible(joined, refs))
            for p in _check_patterns_and_regexps(canon, shown, patterns, regexps):
                for i in r:
                    hits.append(GateHit(i + 1, p, stripped[i][:160]))

    hits.sort(key=lambda h: h.line)
    return GateResult(hits)


_FENCE_RE = re.compile(r"^(?:```|~~~)")
_HEADING_TABLE_RE = re.compile(r"^(?:#{1,6}\s|\|)")
_LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s")


def _paragraphs(raws: list[str], stripped: list[str]) -> list[list[int]]:
    """把行分成 Markdown 段落（行号 0 起）：空行/豁免行/代码围栏结束一段；
    标题与表格行自成一段；列表项各自成段；引用块打断普通段落但连续引用行同段。"""
    out: list[list[int]] = []
    cur: list[int] = []
    fence = False
    quote_block = False

    def close() -> None:
        nonlocal cur, quote_block
        if cur:
            out.append(cur)
        cur = []
        quote_block = False

    for i, raw in enumerate(raws):
        t = raw.strip()
        if _FENCE_RE.match(t):
            close()
            fence = not fence
            continue
        if fence or not stripped[i]:
            close()
            continue
        if _HEADING_TABLE_RE.match(t):
            close()
            out.append([i])
            continue
        quote = t.startswith(">")
        if _LIST_ITEM_RE.match(t) or (quote and not quote_block):
            close()
        if not cur:
            quote_block = quote
        cur.append(i)
    close()
    return out


# ---------------------------------------------------------------------------
# 注册期自检
# ---------------------------------------------------------------------------

def probe_report_line(probe: str) -> str:
    """硬测试往报告里注入探针时的那一整行（自检与真正注入必须用同一个函数拼）。"""
    return f"- 【硬测试注入文本】{probe}(此行用于触发合规 gate,重写时必须删除)"


def validate_gate_rules(
    *,
    patterns: "list[str] | None" = None,
    exempt_lines: "list[str] | None" = None,
    regexps: "list[tuple[str, re.Pattern[str]]] | None" = None,
    probe_line: str = PROBE_LINE,
) -> "list[str] | None":
    """注册期自检：探针包装本身必须不触发（中性对照），真探针必须被拦。

    返回 None = 通过；返回错误清单 = 规则失效或包装污染。自检与真正检查走同一个
    ``compliance_gate`` 判官，防"规则锚定式、自检只测裸探针"这类假绿。
    """
    kwargs = {"patterns": patterns, "exempt_lines": exempt_lines, "regexps": regexps}
    neutral = compliance_gate(probe_report_line("数据核对与证据引用"), **kwargs)
    if not neutral.ok:
        return [f"探针包装本身触发了规则: {neutral.patterns()}（包装文本污染）"]
    real = compliance_gate(probe_report_line(probe_line), **kwargs)
    if real.ok:
        return [f"探针行未被拦截: {probe_line!r}（规则失效）"]
    return None


# ---------------------------------------------------------------------------
# 报告辅助（report 阶段 validator 用）
# ---------------------------------------------------------------------------

_EV_ID_RE = re.compile(r"(?<![0-9A-Za-z_-])ev-[0-9a-f]{6,}(?![0-9A-Za-z_-])")
_CALC_ID_RE = re.compile(r"(?<![0-9A-Za-z_-])calc-[0-9a-f]{16}(?![0-9A-Za-z_-])")


def referenced_ids(report: str) -> dict[str, list[str]]:
    """报告中引用的 ev-/calc- id（带整 token 边界，防伪前缀截断）。"""
    return {
        "evidence": sorted(set(_EV_ID_RE.findall(report))),
        "calculation": sorted(set(_CALC_ID_RE.findall(report))),
    }


_STATUS_TOKEN_RE = re.compile(r"状态[:：]\s*(complete|incomplete|failed|stale)")


def report_status_token(report: str) -> "str | None":
    """报告首行的状态标记。"""
    first = re.split(r"\r?\n", report)[0] if report else ""
    m = _STATUS_TOKEN_RE.search(first)
    return m.group(1) if m else None


def normalize_report_status(report: str, expected: str) -> tuple[str, bool]:
    """把首行状态标记改写为 expected（编排器确定性归一，不动正文）。"""
    lines = re.split(r"\r?\n", report)
    if not lines:
        return report, False
    before = lines[0]
    after = re.sub(r"(状态[:：]\s*)(complete|incomplete|failed|stale)",
                   lambda m: m.group(1) + expected, before)
    if after == before:
        return report, False
    lines[0] = after
    return "\n".join(lines), True


def missing_sections(report: str, sections: list[str]) -> list[str]:
    """报告必须包含的章节标题是否齐全。"""
    missing = []
    for s in sections:
        if not re.search(rf"^#{{1,3}}\s*.*{re.escape(s)}", report, re.MULTILINE):
            missing.append(s)
    return missing
