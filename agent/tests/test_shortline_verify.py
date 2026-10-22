# -*- coding: utf-8 -*-
"""明日验证对账测试：eps 噪声阈值/no_data 不判错且可重对账/防事后不计战绩/
turnover 特例读数/worker 幂等重试/基准发生率校正/复盘服务条件落表。全程无网络。"""

from datetime import date, timedelta

import pytest

from src.data import market_sync_worker as worker_mod
from src.data.market_store import MarketStore
from src.data.trade_calendar import previous_trading_day
from src.product.shortline_verify import (actual_direction, baseline_rate,
                                          conditions_with_status,
                                          has_open_conditions,
                                          insert_conditions, read_metric,
                                          track_record, verify_trade_date)
from src.product.store import ProductStore

T = "2026-07-15"        # 复盘日（周三）
T1 = "2026-07-16"       # 验证日（周四）
EARLY = f"{T}T08:30:00+00:00"     # T 日 16:30 CST 生成 → 不算事后
LATE = f"{T1}T02:00:00+00:00"     # T+1 日 10:00 CST 生成 → 事后补写


def _seed(store: MarketStore, d: str, *, limit_up=58, emotion_avg=2.5,
          themes=7, firstboard=12, turnover=17500.0, kinds="full") -> None:
    if kinds in ("full", "no_emotion"):
        if kinds == "full":
            store.upsert_shortline_snapshot(d, "emotion", {
                "money_effect": {"available": True, "avg": emotion_avg},
                "promotion": {"available": True, "limit_up_count": limit_up,
                              "prev_limit_up_count": limit_up},
                "ladder_gap": {"highest": 4, "tiers": {}, "gaps": []},
            })
        store.upsert_shortline_snapshot(d, "daily", {
            "date": d, "settled": True,
            "readings": {"limit_up": limit_up, "highest_board": 4,
                         "money_effect": emotion_avg, "broken_rate": 0.1},
        })
        store.upsert_shortline_snapshot(d, "facts", {
            "seal_quality": {"total": limit_up, "avg_broken_times": 0.3,
                             "broken_pool": 9},
            "loss_effect": {"limit_down_count": 6, "market_limit_down": 6},
        })
        store.upsert_shortline_snapshot(d, "themes",
                                        {"available": True, "theme_count": themes})
        store.upsert_shortline_snapshot(d, "firstboard",
                                        {"available": True, "total": firstboard})
    store.upsert_market_breadth_snapshot(d, {"turnover_billion": turnover})


def _condition(metric, direction, note=""):
    return {"metric": metric, "direction": direction, "note": note}


class TestDirection:
    def test_verified_mismatch_and_eps_noise_boundary(self, tmp_path):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        _seed(market, T1, limit_up=70, emotion_avg=2.6, themes=8)
        insert_conditions(pstore, "rev-1", T, [
            _condition("limit_up_count", "up"),    # 58→70 差 12 > eps 5 → up ✓
            _condition("theme_count", "up"),       # 7→8 差 1 ≤ eps 2 → flat ✗
            _condition("emotion_avg", "flat"),     # 2.5→2.6 差 0.1 ≤ 0.5 → flat ✓
        ], written_at=EARLY)

        stats = verify_trade_date(pstore, market, T1)
        assert stats["checked"] == 3 and stats["verified"] == 2 \
            and stats["mismatch"] == 1 and stats["no_data"] == 0
        assert stats["remaining"] == 0 and stats["late"] == 0

        with pstore._lock:
            rows = pstore._get_conn().execute(
                "SELECT metric, status, actual, prev_value, cur_value, verified, late "
                "FROM shortline_conditions WHERE source_review_id='rev-1' "
                "ORDER BY rowid").fetchall()
        assert [r["status"] for r in rows] == ["verified", "mismatch", "verified"]
        assert [r["actual"] for r in rows] == ["up", "flat", "flat"]
        assert rows[0]["prev_value"] == 58.0 and rows[0]["cur_value"] == 70.0
        assert rows[0]["verified"] == 1 and rows[1]["verified"] == 0

    def test_no_data_is_not_wrong_and_upgrades_on_retry(self, tmp_path):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        _seed(market, T1)
        market._conn.execute("DELETE FROM shortline_snapshot WHERE trade_date=?", (T1,))
        market._conn.commit()
        insert_conditions(pstore, "rev-2", T, [_condition("emotion_avg", "up")],
                          written_at=EARLY)

        first = verify_trade_date(pstore, market, T1)
        assert first["no_data"] == 1 and first["remaining"] == 1   # 没数据≠判错
        with pstore._lock:
            row = pstore._get_conn().execute(
                "SELECT status, actual FROM shortline_conditions "
                "WHERE source_review_id='rev-2'").fetchone()
        assert row["status"] == "no_data" and row["actual"] is None

        _seed(market, T1, emotion_avg=3.2)                          # 数据补齐
        second = verify_trade_date(pstore, market, T1)
        assert second["checked"] == 1 and second["verified"] == 1
        assert second["remaining"] == 0                             # 升级为已决
        assert not has_open_conditions(pstore, T)

    def test_late_condition_audited_but_not_counted(self, tmp_path):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        _seed(market, T1, limit_up=70)
        insert_conditions(pstore, "rev-3", T, [_condition("limit_up_count", "up")],
                          written_at=LATE)

        stats = verify_trade_date(pstore, market, T1)
        assert stats["verified"] == 1 and stats["late"] == 1        # 照样对账
        with pstore._lock:
            row = pstore._get_conn().execute(
                "SELECT status, verified, late FROM shortline_conditions "
                "WHERE source_review_id='rev-3'").fetchone()
        assert row["status"] == "verified" and row["verified"] == 0  # 不计战绩
        record = track_record(pstore, market)
        assert record["decided"] == 0                                # late 被剔除


class TestReadMetric:
    def test_turnover_uses_breadth_snapshot(self, tmp_path):
        market = MarketStore(tmp_path / "m.db")
        _seed(market, T, turnover=18000.0)
        _seed(market, T1, turnover=17000.0)
        assert read_metric(market, "turnover_total_yi", T) == 18000.0
        assert read_metric(market, "turnover_total_yi", T1) == 17000.0
        assert read_metric(market, "turnover_total_yi", "2020-01-01") is None

    def test_fallback_paths_and_missing(self, tmp_path):
        market = MarketStore(tmp_path / "m.db")
        _seed(market, T, kinds="no_emotion")      # 只删 emotion：daily 兜底
        assert read_metric(market, "limit_up_count", T) == 58.0
        assert read_metric(market, "zt_highest_ladder", T) == 4.0
        assert read_metric(market, "emotion_avg", T) == 2.5
        assert read_metric(market, "theme_count", T) == 7.0
        assert read_metric(market, "zb_count", T) == 9.0
        assert read_metric(market, "limit_up_count", "2020-01-01") is None

    def test_actual_direction_eps_semantics(self):
        assert actual_direction(70, 58, 5) == "up"
        assert actual_direction(50, 58, 5) == "down"
        assert actual_direction(62.9, 58, 5) == "flat"
        assert actual_direction(None, 58, 5) is None
        assert actual_direction(70, None, 5) is None


class TestWorkerHook:
    def test_retries_no_data_then_idempotent_key(self, tmp_path, monkeypatch):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        insert_conditions(pstore, "rev-4", T, [_condition("theme_count", "down")],
                          written_at=EARLY)
        monkeypatch.setattr(worker_mod, "_settled_trade_date", lambda store=None: T1)
        monkeypatch.setattr(worker_mod, "_product_store_for_verify", lambda: pstore)

        worker_mod._maybe_run_shortline_verify(market)   # t1 数据未齐 → no_data
        assert market.get_meta(f"daemon:verify:{T1}") is None
        assert has_open_conditions(pstore, T)

        _seed(market, T1, themes=3)                        # 差 4 > eps 2 → down ✓
        worker_mod._maybe_run_shortline_verify(market)
        assert market.get_meta(f"daemon:verify:{T1}")      # 全决 → 落幂等键
        assert not has_open_conditions(pstore, T)

        market.set_meta("daemon:probe-tamper", "1")        # 第三次：键在，直接跳过
        before = market.get_meta(f"daemon:verify:{T1}")
        worker_mod._maybe_run_shortline_verify(market)
        assert market.get_meta(f"daemon:verify:{T1}") == before

    def test_no_conditions_stamps_key_immediately(self, tmp_path, monkeypatch):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        monkeypatch.setattr(worker_mod, "_settled_trade_date", lambda store=None: T1)
        monkeypatch.setattr(worker_mod, "_product_store_for_verify", lambda: pstore)
        worker_mod._maybe_run_shortline_verify(market)
        assert market.get_meta(f"daemon:verify:{T1}")      # T 无条件 → 直接记键


class TestBaseline:
    def test_expected_rate_and_edge_correction(self, tmp_path):
        """连涨历史里预测 up 每次都中，但基准也是 100% → edge = 0（不等于有水平）。

        日期从真实交易日链倒推（不赌日历源/节假日）。
        """
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        t1 = previous_trading_day(date.today().isoformat())
        chain = [t1]
        for _ in range(15):
            chain.append(previous_trading_day(chain[-1]))
        days = list(reversed(chain))                  # 升序连续交易日；末位 = T
        t_day = days[-2]
        for i, d in enumerate(days[:-1]):
            _seed(market, d, limit_up=40 + i * 20)
        _seed(market, t1, limit_up=40 + (len(days) - 1) * 20)
        insert_conditions(pstore, "rev-5", t_day,
                          [_condition("limit_up_count", "up")],
                          written_at=f"{t_day}T08:30:00+00:00")
        stats = verify_trade_date(pstore, market, t1)
        assert stats["checked"] == 1 and stats["verified"] == 1, stats

        rate, sample = baseline_rate(market, "limit_up_count", "up")
        assert sample >= 12 and rate == pytest.approx(1.0)

        record = track_record(pstore, market)
        metric = record["by_metric"]["limit_up_count"]
        assert metric["decided"] == 1 and metric["hits"] == 1
        up = metric["by_direction"]["up"]
        assert up["expected_rate"] == pytest.approx(1.0)
        assert up["edge"] == pytest.approx(1 - 1 * 1.0)     # 命中 1 次，edge 归零

    def test_baseline_below_min_sample_is_none(self, tmp_path):
        market = MarketStore(tmp_path / "m.db")
        t1 = previous_trading_day(date.today().isoformat())
        chain = [t1]
        for _ in range(4):
            chain.append(previous_trading_day(chain[-1]))
        for d in chain[:-1]:                              # 只有 4 对 → 样本不足
            _seed(market, d, limit_up=50)
        rate, sample = baseline_rate(market, "limit_up_count", "up")
        assert rate is None and sample < 12


class TestAttach:
    def test_conditions_with_status_and_legacy_passthrough(self, tmp_path):
        pstore, market = ProductStore(tmp_path / "p.db"), MarketStore(tmp_path / "m.db")
        _seed(market, T)
        _seed(market, T1, limit_up=70)
        conds = [_condition("limit_up_count", "up", note="情绪不退")]
        insert_conditions(pstore, "rev-6", T, conds, written_at=EARLY)
        verify_trade_date(pstore, market, T1)

        enriched = conditions_with_status(pstore, "rev-6", conds)
        assert enriched[0]["verification"]["status"] == "verified"
        assert enriched[0]["verification"]["actual"] == "up"
        assert enriched[0]["note"] == "情绪不退"

        # 旧复盘没有对账行（行数对不上）→ 原样返回
        legacy = [_condition("theme_count", "down")]
        assert conditions_with_status(pstore, "rev-legacy", legacy) is legacy


class TestServiceWritePoint:
    def test_review_generation_persists_pending_conditions(self, tmp_path):
        from tests.test_shortline_review import _full_llm, _reader
        from src.product.shortline_review import ShortlineReviewService

        pstore = ProductStore(tmp_path / "p.db")
        llm = _full_llm()
        svc = ShortlineReviewService(pstore, lambda: llm,
                                     snapshot_reader=_reader(), background=False)
        row = svc.start()
        assert row["status"] == "completed", row["error"]

        with pstore._lock:
            cond = pstore._get_conn().execute(
                "SELECT trade_date, metric, direction, status, written_at "
                "FROM shortline_conditions WHERE source_review_id=?",
                (row["id"],)).fetchall()
        assert len(cond) == 1
        assert cond[0]["trade_date"] == row["trade_date"]
        assert cond[0]["metric"] == "limit_up_count"
        assert cond[0]["direction"] == "down"
        assert cond[0]["status"] == "pending"
        assert cond[0]["written_at"]
        assert has_open_conditions(pstore, row["trade_date"])
