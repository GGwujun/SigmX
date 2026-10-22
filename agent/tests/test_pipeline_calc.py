# -*- coding: utf-8 -*-
"""calc 确定性计算核心测试。"""

import math

import pytest

from src.research_pipeline.calc import (
    CALC_VERSION,
    calculation_id,
    list_functions,
    register_calc,
    run_calc,
    verify_calc,
    verify_calcs,
)


class TestCalculationId:
    def test_deterministic(self):
        assert calculation_id("mean", {"series": [1, 2, 3]}) == calculation_id("mean", {"series": [1, 2, 3]})

    def test_different_args_different_id(self):
        assert calculation_id("mean", {"series": [1, 2, 3]}) != calculation_id("mean", {"series": [1, 2, 4]})

    def test_different_fn_different_id(self):
        assert calculation_id("mean", {"series": [1]}) != calculation_id("sum", {"series": [1]})

    def test_float_int_canonicalized(self):
        assert calculation_id("ratio", {"a": 1.0, "b": 2}) == calculation_id("ratio", {"a": 1, "b": 2.0})

    def test_dict_key_order_irrelevant(self):
        assert calculation_id("f", {"a": 1, "b": 2}) == calculation_id("f", {"b": 2, "a": 1})

    def test_id_format(self):
        cid = calculation_id("mean", {"series": [1]})
        assert cid.startswith("calc-") and len(cid) == len("calc-") + 16


class TestRunCalc:
    def test_pct_change(self):
        env = run_calc("pct_change", {"a": 110, "b": 100})
        assert env["status"] == "ok" and env["unit"] == "%"
        assert math.isclose(env["value"], 10.0)

    def test_ratio_zero_division(self):
        env = run_calc("ratio", {"a": 1, "b": 0})
        assert env["status"] == "error" and "ZeroDivision" in env["reason"]

    def test_unknown_function(self):
        env = run_calc("no_such_fn", {"a": 1})
        assert env["status"] == "error" and "未知函数" in env["reason"]

    def test_bad_args(self):
        env = run_calc("mean", {"series": "not-a-list"})
        assert env["status"] == "error"
        env = run_calc("mean", {})
        assert env["status"] == "error"

    def test_percentile_rank(self):
        env = run_calc("percentile_rank", {"value": 15, "series": [10, 20, 30, 40]})
        assert env["status"] == "ok"
        assert math.isclose(env["value"], 25.0) and env["unit"] == "%"

    def test_max_drawdown(self):
        env = run_calc("max_drawdown", {"series": [100, 120, 60, 90]})
        assert env["status"] == "ok"
        assert math.isclose(env["value"], 50.0)

    def test_volatility_zero_series(self):
        env = run_calc("volatility", {"series": [5, 5, 5, 5]})
        assert env["status"] == "ok" and env["value"] == 0.0

    def test_zscore(self):
        env = run_calc("zscore", {"value": 3.0, "series": [1.0, 2.0, 3.0, 4.0]})
        assert env["status"] == "ok"
        # mean=2.5, pstdev=sqrt(1.25)≈1.118 → (3-2.5)/1.118
        assert math.isclose(env["value"], 0.4472135954999579, rel_tol=1e-6)

    def test_list_meta_command(self):
        out = run_calc("list", {})
        names = [f["name"] for f in out["functions"]]
        assert "mean" in names and "pct_change" in names

    def test_envelope_fields(self):
        env = run_calc("diff", {"a": 5, "b": 3})
        assert set(env) >= {"calculation_id", "fn", "args", "status", "value", "unit",
                            "reason", "details", "calc_version", "created_at"}
        assert env["fn"] == "diff" and env["calc_version"] == CALC_VERSION

    def test_plugin_registration(self):
        @register_calc("_test_double", doc="翻倍")
        def _double(args: dict):
            return float(args["x"]) * 2, ""
        try:
            env = run_calc("_test_double", {"x": 21})
            assert env["status"] == "ok" and env["value"] == 42
            assert any(f["name"] == "_test_double" for f in list_functions())
        finally:
            from src.research_pipeline import calc as calc_mod
            calc_mod._REGISTRY.pop("_test_double", None)


class TestVerifyCalc:
    def test_recompute_consistent(self):
        env = run_calc("mean", {"series": [1, 2, 3, 4]})
        assert verify_calc(env) is True

    def test_tampered_value_detected(self):
        env = run_calc("mean", {"series": [1, 2, 3, 4]})
        env["value"] = 999.0
        assert verify_calc(env) is False

    def test_tampered_unit_detected(self):
        env = run_calc("pct_change", {"a": 110, "b": 100})
        env["unit"] = "元"
        assert verify_calc(env) is False

    def test_error_record_consistent(self):
        env = run_calc("ratio", {"a": 1, "b": 0})
        assert env["status"] == "error"
        assert verify_calc(env) is True

    def test_version_mismatch_skipped(self):
        env = run_calc("mean", {"series": [1, 2]})
        env["calc_version"] = "0"
        assert verify_calc(env) is None

    def test_float_tolerance(self):
        env = run_calc("ratio", {"a": 1, "b": 3})
        env["value"] = env["value"] + 1e-15  # 远小于相对容差
        assert verify_calc(env) is True

    def test_verify_calcs_batch(self):
        good = run_calc("mean", {"series": [1, 2, 3]})
        bad = run_calc("sum", {"series": [1, 2, 3]})
        bad["value"] = 100.0
        out = verify_calcs([good, bad])
        assert len(out) == 1 and out[0]["fn"] == "sum"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
