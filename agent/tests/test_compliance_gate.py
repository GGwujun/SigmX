# -*- coding: utf-8 -*-
"""合规 gate 测试：三重检查各攻击向量 + probe 自检（移植自 VA gate 审计用例）。"""

import pytest

from src.compliance.gate import (
    canonical_for_gate,
    compliance_gate,
    markdown_visible,
    missing_sections,
    normalize_report_status,
    probe_report_line,
    referenced_ids,
    report_status_token,
    validate_gate_rules,
)
from src.compliance.gate_rules import PATTERNS, gate_stage_patterns


# ---------------------------------------------------------------------------
# 规范形
# ---------------------------------------------------------------------------

class TestCanonicalForGate:
    def test_plain_passthrough(self):
        assert canonical_for_gate("正常文本") == "正常文本"

    def test_space_between_cjk_stripped(self):
        # 汉字之间的空格/全角空格/间隔号忽略
        assert canonical_for_gate("建 仓") == "建仓"
        assert canonical_for_gate("建　仓") == "建仓"
        assert canonical_for_gate("建·仓") == "建仓"
        assert canonical_for_gate("建-仓") == "建仓"

    def test_zero_width_stripped(self):
        assert canonical_for_gate("建​仓") == "建仓"
        assert canonical_for_gate("建﻿仓") == "建仓"

    def test_traditional_to_simplified(self):
        assert canonical_for_gate("建倉") == "建仓"
        assert canonical_for_gate("目標價") == "目标价"

    def test_fullwidth_normalized(self):
        # NFKC：全角字母/数字归半角
        assert canonical_for_gate("ＢＵＹ") == "BUY"

    def test_cjk_sep_not_stripped_outside_cjk(self):
        # 分隔符两侧不是汉字时不剥（数字/字母间的连字符是语义的一部分）
        assert canonical_for_gate("PE-TTM") == "PE-TTM"

    def test_combining_mark_stripped(self):
        assert canonical_for_gate("建́仓") == "建仓"


# ---------------------------------------------------------------------------
# 渲染后可见文字
# ---------------------------------------------------------------------------

class TestMarkdownVisible:
    def test_link_display_text_kept(self):
        assert markdown_visible("前[建](https://x)仓") == "前建仓"

    def test_nested_image_in_link(self):
        assert markdown_visible("[![alt](img.png)](url)") == "alt"

    def test_backticks_stripped(self):
        assert markdown_visible("`建仓`") == "建仓"

    def test_html_tag_stripped(self):
        assert markdown_visible("<b>建仓</b>") == "建仓"

    def test_numeric_entity_decoded(self):
        assert markdown_visible("&#24314;仓") == "建仓"  # 24314 = 建
        assert markdown_visible("&#x5efa;仓") == "建仓"

    def test_named_entity_decoded(self):
        assert markdown_visible("&amp;") == "&"

    def test_backslash_escape_decoded(self):
        # Markdown 转义只对 ASCII 标点有意义；汉字前的反斜杠不是转义
        assert markdown_visible("\\*") == "*"
        assert markdown_visible("\\建\\仓") == "\\建\\仓"

    def test_reference_label_expands_only_when_defined(self):
        # 缩写 [建] 只有别处有 [建]: url 定义时才显示为「建」
        refs = {"建"}
        assert markdown_visible("[建]仓", refs) == "建仓"
        assert markdown_visible("[建]仓", frozenset()) == "[建]仓"


# ---------------------------------------------------------------------------
# 主判官
# ---------------------------------------------------------------------------

class TestComplianceGate:
    def test_clean_report_passes(self):
        report = "公司营收 12.3 亿元，同比增长 4.5%。\n\n数据来自财报 [ev-abc123]。\n\n本报告不提供任何投资动作建议。"
        assert compliance_gate(report).ok

    def test_blatant_advice_blocked(self):
        res = compliance_gate("建议建仓并设目标价")
        assert not res.ok
        assert "建仓" in res.patterns()

    def test_zero_width_evade_blocked(self):
        assert not compliance_gate("建议建​仓").ok

    def test_traditional_evade_blocked(self):
        assert not compliance_gate("建议建倉").ok

    def test_separator_evade_blocked(self):
        assert not compliance_gate("建议建·仓").ok

    def test_link_split_word_blocked(self):
        # 禁词被链接拆开：原文无连续禁词，渲染后是连起来的
        res = compliance_gate("建议前[建](https://x)仓操作")
        assert not res.ok

    def test_entity_evade_blocked(self):
        assert not compliance_gate("建议&#24314;仓").ok

    def test_escaped_evade_blocked(self):
        assert not compliance_gate("建议`建仓`").ok

    def test_html_wrap_blocked(self):
        assert not compliance_gate("建议<b>建仓</b>").ok

    def test_exempt_line_exact_passes(self):
        res = compliance_gate("本报告不提供任何投资动作建议。")
        assert res.ok

    def test_exempt_flip_not_forgiven(self):
        # 半句翻转：不精确等于免责声明 → 不豁免
        res = compliance_gate("本报告不构成投资建议,但建议建仓。")
        assert not res.ok

    def test_regex_action_advice(self):
        assert not compliance_gate("业绩稳定，值得买入").ok

    def test_regex_breakdown_exit(self):
        assert not compliance_gate("跌破 80 元止损离场").ok

    def test_regex_en_sentence_start(self):
        assert not compliance_gate("Note: buy AAPL now").ok

    def test_regex_en_target_price(self):
        assert not compliance_gate("The target price is 120.").ok

    def test_regex_immediate_action_after_punct(self):
        # 时机+动作（消费前缀版）：标点后接时机词+动作
        assert not compliance_gate("机会来了，立即买入。").ok
        assert not compliance_gate("大家现在买入。").ok

    def test_regex_suggest_condition_action(self):
        # 建议与动作之间隔一段条件（同一分句内）
        assert not compliance_gate("建议在回调后买入该标的").ok

    def test_regex_price_prediction(self):
        assert not compliance_gate("预计该股明天会大涨。").ok

    def test_factual_statement_not_blocked(self):
        # 事实/统计陈述不拦：机构评级分布统计、历史行情
        report = "机构评级分布：买入评级 31 篇。\n去年股价上涨 30%。\n北向资金今日买入 2.1 亿元。"
        assert compliance_gate(report).ok

    def test_paragraph_join_across_lines(self):
        # 跨行拼接：每行单独都不含完整禁词，段落 join 后才是（"建议买"）
        report = "综上所述建议\n买入该股。"
        res = compliance_gate(report)
        assert not res.ok
        # 拼出来命中的，这几行每行都记一条
        assert {h.line for h in res.hits} == {1, 2}

    def test_paragraph_join_blocked_by_hit_line(self):
        # 已命中的行当分隔：第一行命中后，后两行不再与更早行拼接
        report = "建议建仓。\n综上所述建议\n逢低布局。"
        res = compliance_gate(report)
        assert not res.ok
        assert 1 in {h.line for h in res.hits}
        assert 2 not in {h.line for h in res.hits} or 3 not in {h.line for h in res.hits}

    def test_code_fence_not_joined(self):
        # fence 只隔断跨行拼接（逐行照查），拆开的字在 fence 里拼不起来
        report = "```\n建\n仓\n```"
        assert compliance_gate(report).ok

    def test_list_prefix_stripped(self):
        assert not compliance_gate("- 建议建仓").ok
        assert not compliance_gate("1. 建议建仓").ok

    def test_gt_number_not_treated_as_quote(self):
        # `>18%` 是"大于"语义，剥前缀不影响命中判断——但也不误造命中
        assert compliance_gate("涨幅 >18% 的样本").ok

    def test_stage_patterns_narrowed(self):
        # 阶段收窄版：目标价/止损/止盈不作裸子串拦截，其余不变
        assert "目标价" in PATTERNS
        assert "目标价" not in gate_stage_patterns()
        assert "建仓" in gate_stage_patterns()
        # 收窄版仍拦得住带动作语气的句子（正则表不变）
        assert not compliance_gate("建议建仓 30%", patterns=gate_stage_patterns()).ok

    def test_hit_line_numbers_and_text(self):
        res = compliance_gate("第一行没问题。\n第二行建议建仓。")
        assert not res.ok
        assert res.hits[0].line == 2
        assert "第二行" in res.hits[0].text


# ---------------------------------------------------------------------------
# probe 自检
# ---------------------------------------------------------------------------

class TestProbeSelfCheck:
    def test_default_rules_pass_self_check(self):
        assert validate_gate_rules() is None

    def test_broken_rules_detected(self):
        # 空规则表：真探针拦不住 → 自检必须报错
        errors = validate_gate_rules(patterns=[], regexps=[])
        assert errors and "未被拦截" in errors[0]

    def test_probe_wrapper_neutral_and_probe_blocked(self):
        # 自检两分支的真身：中性包装干净、真探针被拦
        assert compliance_gate(probe_report_line("数据核对与证据引用")).ok
        assert not compliance_gate(probe_report_line("建议建仓并设目标价")).ok


# ---------------------------------------------------------------------------
# 报告辅助
# ---------------------------------------------------------------------------

class TestReportHelpers:
    def test_referenced_ids_with_token_boundary(self):
        # 伪前缀截断：ev-abcdef123456xyz 不是合法引用（边界断言失败）
        assert referenced_ids("见 ev-abcdef123456xyz") == {"evidence": [], "calculation": []}
        assert referenced_ids("见 ev-abcdef123456。") == {"evidence": ["ev-abcdef123456"], "calculation": []}
        assert referenced_ids("算 calc-0123456789abcdef 处") == {
            "evidence": [], "calculation": ["calc-0123456789abcdef"]}

    def test_report_status_token(self):
        assert report_status_token("状态: complete\n正文") == "complete"
        assert report_status_token("状态：incomplete") == "incomplete"
        assert report_status_token("普通首行") is None

    def test_normalize_report_status(self):
        text, changed = normalize_report_status("状态: complete\n正文", "incomplete")
        assert changed and text.startswith("状态: incomplete")
        text, changed = normalize_report_status("普通首行", "failed")
        assert not changed

    def test_missing_sections(self):
        report = "# 结论\n...\n## 风险\n..."
        assert missing_sections(report, ["结论", "风险"]) == []
        assert missing_sections(report, ["估值"]) == ["估值"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
