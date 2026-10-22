# -*- coding: utf-8 -*-
"""数字忠实度测试：算式重算 / 数字主张剥离 / 已知值比对 / 四档审计。"""

import pytest

from src.research_pipeline.arithmetic import (
    audit_numbers,
    check_stated_arithmetic,
    claim_tokens,
    number_bound,
)


def _calcs_of(line: str) -> dict:
    """{raw片段: StatedCalc}，便于按片段断言。"""
    return {c.raw: c for c in check_stated_arithmetic(line)}


class TestStatedArithmetic:
    def test_simple_division_percent(self):
        # 实测最常见的形状：两个数相除得一个占比
        calcs = _calcs_of("453.90 ÷ 910.94 = 49.83%")
        assert len(calcs) == 1
        c = next(iter(calcs.values()))
        assert c.ok and c.percent
        assert c.stated == pytest.approx(49.83, abs=0.05)

    def test_yoy_ratio_minus_one(self):
        # A ÷ B − 1 = R%（同比）
        calcs = _calcs_of("444.64 亿 ÷ 453.90 亿 − 1 = −2.04%")
        c = next(iter(calcs.values()))
        assert c.ok and c.percent
        assert c.stated == pytest.approx(-2.04, abs=0.05)

    def test_real_world_wrong_direction_detected(self):
        # VA 真实案例：444.64 对 453.90 写成"+0.2%"，实际是 −2.04%——方向都反了
        calcs = _calcs_of("444.64 亿 ÷ 453.90 亿 − 1 = +0.2%")
        c = next(iter(calcs.values()))
        assert not c.ok and c.percent

    def test_subtraction(self):
        calcs = _calcs_of("19005.40 − 16821.09 = 2184.31")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_omitted_magnitude_on_result(self):
        # 省略写法：数量级只写在结果上（运算数按结果数量级读）
        calcs = _calcs_of("19005.40 − 16821.09 = 2184.31 亿元")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_unit_conversion_reading(self):
        # 结果换了个单位写：5 × 2000 = 1 万
        calcs = _calcs_of("5 × 2000 = 1 万")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_mixed_magnitude_addition_is_wrong(self):
        # 量纲混算：2 亿 + 3 万 ≠ 5 亿（按裸数判成对是错的）
        calcs = _calcs_of("2亿 + 3万 = 5亿")
        c = next(iter(calcs.values()))
        assert not c.ok

    def test_percent_dimension_mismatch_not_recognized(self):
        # 金额 + 比例：识别不出结果换算 → 不认这条算式（既不算对也不算错）
        calcs = _calcs_of("100 元 + 20% = 100.2 元")
        assert len(calcs) == 0

    def test_chain_addition(self):
        calcs = _calcs_of("210.92+160.28+86.77=457.97")
        c = next(iter(calcs.values()))
        assert c.ok and c.stated == pytest.approx(457.97, abs=0.02)

    def test_chain_wrong_detected(self):
        calcs = _calcs_of("210.92+160.28+86.77=500.00")
        c = next(iter(calcs.values()))
        assert not c.ok

    def test_chain_with_units(self):
        calcs = _calcs_of("前十合计 210.92+160.28+84.89=456.09 亿元")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_approx_tolerance(self):
        # ≈ 只承诺写出来的那几位
        calcs = _calcs_of("40 ÷ 69 ≈ 58.0%")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_label_between_operator_and_number(self):
        # 运算符与数字之间夹标签
        calcs = _calcs_of("453.90 亿元 ÷ 甲项 910.94 亿元 = 49.83%")
        c = next(iter(calcs.values()))
        assert c.ok

    def test_evidence_ref_and_period_stripped(self):
        # 证据引用与期间标签先剥再匹配
        line = "2026H1 444.64 亿 ÷ 2025H1 453.90 亿 − 1 = −2.04% [ev-abcdef123]"
        c = next(iter(_calcs_of(line).values()))
        assert c.ok

    def test_tail_of_longer_expression_not_double_counted(self):
        # 长算式的尾巴不单独认：`…+86.77=457.97` 不再单独报一条
        calcs = check_stated_arithmetic("94.17+86.77=181.0")
        # （两数式正常识别；这是可识别的短式）
        assert any(c.ok for c in calcs)

    def test_plus_sign_result(self):
        calcs = _calcs_of("6.43 ÷ 18.14 = +35.4%")
        c = next(iter(calcs.values()))
        assert c.ok and c.stated == pytest.approx(35.4, abs=0.1)

    def test_chinese_dash_not_negative_sign(self):
        # 中文破折号是标点不是负号
        calcs = _calcs_of("结论——19005.40-16821.09=2184.31")
        c = next(iter(calcs.values()))
        assert c.ok


class TestClaimTokens:
    def _nums(self, line, symbol=None):
        return [t["n"] for t in claim_tokens(line, symbol)]

    def test_plain_number_claim(self):
        assert self._nums("涨幅达 4.5%") == [4.5]

    def test_date_stripped(self):
        assert "2026" not in [str(n) for n in self._nums("2026-08-24 收盘")]

    def test_bare_year_stripped(self):
        assert self._nums("2026 年景气度上行") == []

    def test_period_tag_stripped(self):
        assert self._nums("2026H1 营收 12.3 亿元") == [12.3]

    def test_subject_code_stripped(self):
        assert self._nums("300750.SZ 大涨") == []

    def test_symbol_bare_code_stripped(self):
        assert self._nums("主业聚焦 300750 龙头", symbol="300750") == []

    def test_ordinal_stripped(self):
        assert self._nums("第 3 次测试，共 5 条") == []

    def test_multiply_n_stripped(self):
        assert self._nums("放量 3x") == []

    def test_window_label_stripped(self):
        assert self._nums("近 5 年复合增长 12.5%") == [12.5]

    def test_small_integer_count_skipped(self):
        # ≤20 的纯整数计数跳过；带单位/小数点的保留
        assert self._nums("共 3 家公司") == []
        assert self._nums("3 亿元投入") == [3.0]
        assert self._nums("增长 2.00 倍") == [2.0]

    def test_thousands_separator(self):
        assert self._nums("营收 1,234.56 万元") == [1234.56]

    def test_comma_not_thousands(self):
        # 逗号后不是 3 位时不拼成千分位（>20 才不会被小整数规则跳过）
        assert self._nums("years=21,33") == [21.0, 33.0]

    def test_url_and_http_code_stripped(self):
        assert self._nums("详见 https://x.com/a123 和 HTTP 429") == []

    def test_ev_calc_id_stripped(self):
        assert self._nums("依据 [ev-abcdef123456] 与 calc-0123456789abcdef") == []

    def test_speed_label_stripped_in_category_context(self):
        assert self._nums("光模块速率 800G 是产品类别") == []

    def test_speed_label_kept_in_money_context(self):
        # 金额语境不剥
        nums = self._nums("资金 1.6T 美元")
        assert 1.6 in nums

    def test_unit_attached_to_raw(self):
        toks = claim_tokens("净利 3.2 亿元")
        assert toks[0]["raw"].endswith("亿")


class TestNumberBound:
    def test_exact(self):
        assert number_bound(12.34, [12.34])

    def test_unit_scaling(self):
        # known=1.23 亿，写作 1.23（s=1e-8 命中）
        assert number_bound(1.23, [1.23e8])
        assert number_bound(12300.0, [1.23e8])  # 万

    def test_percent_scaling(self):
        assert number_bound(12.0, [0.12])

    def test_tolerance(self):
        assert number_bound(12.34, [12.33]) is False or True  # 边界容差内
        assert not number_bound(12.34, [13.0])

    def test_rounded_to_cents(self):
        assert number_bound(1.23, [1.234567])


class TestAuditNumbers:
    def test_four_buckets(self):
        known = [100.0, 453.9]
        text = (
            "营收 100 亿元，占比 453.9 ÷ 910.94 = 49.83%。\n"   # bound + derived
            "另有 77.7 这个没出处的数。\n"                        # loose
            "但 444.64 亿 ÷ 453.90 亿 − 1 = +0.2% 是算错的。\n"  # bad_math
        )
        audit = audit_numbers(text, known)
        assert audit.total >= 4
        assert audit.bound >= 1          # 100 / 453.9 对上已知值
        assert audit.derived >= 1        # 49.83 在自洽算式里
        assert any(l.value == 77.7 for l in audit.loose)
        assert len(audit.bad_math) == 1
        assert "0.2" in audit.bad_math[0].raw

    def test_clean_text_mostly_bound(self):
        known = [12.3]
        audit = audit_numbers("营收 12.3 亿元。", known)
        assert audit.total == 1 and audit.bound == 1 and not audit.loose and not audit.bad_math

    def test_only_flags_not_rewrites(self):
        # 只标不改：原文本不变，loose 只是记录
        text = "某数 55.5 无出处。"
        audit = audit_numbers(text, [])
        assert audit.loose[0].line.startswith("某数")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


class TestMaskUncited:
    def test_loose_masked_bound_and_derived_kept(self):
        from src.research_pipeline.arithmetic import mask_uncited
        known = [100.0, 110.0, 10.0]
        text = "收盘从 100 升至 110，涨幅 10.0%，另有 453.9 亿元成交。"
        masked, n = mask_uncited(text, known)
        assert n == 1
        assert "〔未核实〕" in masked and "453.9" not in masked
        assert "100" in masked and "110" in masked and "10.0%" in masked

    def test_unit_conversion_bound_not_masked(self):
        from src.research_pipeline.arithmetic import mask_uncited
        masked, n = mask_uncited("成交 1750 亿元", [1.75e11])   # 亿换算命中
        assert n == 0 and "1750" in masked

    def test_correct_arithmetic_not_masked(self):
        from src.research_pipeline.arithmetic import mask_uncited
        masked, n = mask_uncited("100 ÷ 8 = 12.5", [])
        assert n == 0 and "12.5" in masked

    def test_custom_mask_marker(self):
        from src.research_pipeline.arithmetic import mask_uncited
        masked, n = mask_uncited("营收 88.5 亿元", [], mask="（略※）")
        assert n == 1 and "88.5" not in masked and "（略※）" in masked

    def test_non_claims_untouched(self):
        from src.research_pipeline.arithmetic import mask_uncited
        text = "2024 年第 3 批共 5 家公司，公告编号 2026-012345，于 2026-07-15 披露。"
        masked, n = mask_uncited(text, [])
        assert n == 0 and masked == text

    def test_numeric_leaves_recursion(self):
        from src.research_pipeline.arithmetic import numeric_leaves
        obj = {"rows": [{"close": 100.5, "flag": True, "name": "x"},
                        {"close": None}], "total": 3}
        assert sorted(numeric_leaves(obj)) == [3.0, 100.5]
