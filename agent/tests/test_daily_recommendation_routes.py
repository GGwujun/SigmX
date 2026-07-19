from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from fastapi import HTTPException

from src.api import daily_recommendation_routes as routes
from src.data.market_quality import DataReadiness, QualityStatus


class _FakeStore:
    def __init__(self, status: QualityStatus = QualityStatus.PUBLISHED):
        self.status = status

    def get_data_readiness(self, dataset: str, as_of: str) -> DataReadiness:
        return DataReadiness(
            dataset=dataset,
            as_of=as_of,
            status=self.status,
            expected_rows=1,
            valid_rows=1 if self.status is QualityStatus.PUBLISHED else 0,
            published_rows=1 if self.status is QualityStatus.PUBLISHED else 0,
            source="tushare.daily",
            run_id="run-1",
            blocking_reasons=[] if self.status is QualityStatus.PUBLISHED else ["unexplained_missing_codes"],
        )

    def get_latest_realtime_quote(self, code: str, trade_date: str | None = None):
        return {
            "trade_date": trade_date,
            "code": code,
            "price": 12.34,
            "rise_rate": 2.5,
            "source": "test",
        }

    def get_recommendation_history_coverage(self, min_bars: int = 60):
        return {"active_codes": 4000, "covered_codes": 3990, "coverage": 0.9975}


def test_candidate_market_data_freshness_rejects_unverified_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _FakeStore(QualityStatus.PARTIAL))
    monkeypatch.setattr(routes, "_expected_settled_date", lambda store: "2026-07-14")

    with pytest.raises(HTTPException) as exc:
        routes._assert_candidate_market_data_fresh()

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "DATA_NOT_READY"
    assert exc.value.detail["status"] == "partial"


def test_candidate_market_data_freshness_allows_published_exact_date(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _FakeStore(QualityStatus.PUBLISHED))
    monkeypatch.setattr(routes, "_expected_settled_date", lambda store: "2026-07-14")

    routes._assert_candidate_market_data_fresh()


def test_candidate_market_data_freshness_rejects_incomplete_history(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    store = _FakeStore(QualityStatus.PUBLISHED)
    store.get_recommendation_history_coverage = lambda min_bars=60: {
        "active_codes": 4000,
        "covered_codes": 1200,
        "coverage": 0.3,
    }
    monkeypatch.setattr(market_store, "get_market_store", lambda: store)
    monkeypatch.setattr(routes, "_expected_settled_date", lambda value: "2026-07-14")

    with pytest.raises(HTTPException) as exc:
        routes._assert_candidate_market_data_fresh()

    assert exc.value.detail["dataset"] == "bars_daily_history"
    assert "history_coverage_below_threshold" in exc.value.detail["blocking_reasons"]


def test_refresh_candidate_quote_uses_today_realtime_price(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _FakeStore())
    monkeypatch.setattr(routes, "_today_cst", lambda: "2026-07-02")

    item = routes._refresh_candidate_quote({"symbol": "600000.SH", "price": 10.0, "change_pct": -1.0})

    assert item["price"] == 12.34
    assert item["change_pct"] == 2.5
    assert item["quote_source"] == "test"


class _QuoteStore(_FakeStore):
    def __init__(self, quote):
        super().__init__()
        self.quote = quote

    def get_latest_realtime_quote(self, code: str, trade_date: str | None = None):
        return self.quote


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 14, hour, minute, tzinfo=routes._CST)


def _quote(*, snapshot_at: str = "2026-07-14T09:27:00+08:00") -> dict:
    return {
        "trade_date": "2026-07-14",
        "code": "600000.SH",
        "price": 12.34,
        "pre_close": 12.0,
        "high": 12.5,
        "low": 11.9,
        "volume": 1000.0,
        "rise_rate": 2.833,
        "snapshot_at": snapshot_at,
        "source": "test.realtime",
    }


def test_validated_realtime_quote_rejects_missing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _QuoteStore(None))

    with pytest.raises(HTTPException) as exc:
        routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "DATA_NOT_READY"
    assert exc.value.detail["blocking_reasons"] == ["realtime_snapshot_missing"]


def test_validated_realtime_quote_rejects_stale_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(
        market_store,
        "get_market_store",
        lambda: _QuoteStore(_quote(snapshot_at="2026-07-14T09:20:00+08:00")),
    )

    with pytest.raises(HTTPException) as exc:
        routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))

    assert exc.value.status_code == 503
    assert "realtime_snapshot_stale" in exc.value.detail["blocking_reasons"]


@pytest.mark.parametrize(
    ("quote", "reason"),
    [
        (_quote(snapshot_at="2026-07-14T09:28:00+08:00"), "realtime_snapshot_from_future"),
        ({**_quote(), "trade_date": "2026-07-13"}, "realtime_trade_date_mismatch"),
        ({**_quote(), "price": 0.0}, "realtime_price_invalid"),
        ({**_quote(), "pre_close": 0.0}, "realtime_pre_close_invalid"),
        ({**_quote(), "volume": 0.0}, "realtime_volume_invalid"),
    ],
)
def test_validated_realtime_quote_rejects_invalid_fields(
    monkeypatch: pytest.MonkeyPatch,
    quote: dict,
    reason: str,
) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _QuoteStore(quote))

    with pytest.raises(HTTPException) as exc:
        routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))

    assert reason in exc.value.detail["blocking_reasons"]


def test_validated_realtime_quote_returns_auditable_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _QuoteStore(_quote()))

    item = routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))

    assert item["price"] == 12.34
    assert item["high"] == 12.5
    assert item["low"] == 11.9
    assert item["volume"] == 1000.0
    assert item["market_context"] == {
        "trade_date": "2026-07-14",
        "snapshot_at": "2026-07-14T09:27:00+08:00",
        "snapshot_age_seconds": 0.0,
        "quote_source": "test.realtime",
        "valid": True,
    }


def test_candidate_pool_does_not_fall_back_to_daily_close(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.opportunity_routes as opportunity_routes
    import src.data.market_store as market_store

    monkeypatch.setattr(routes, "_assert_candidate_market_data_fresh", lambda: None)
    monkeypatch.setattr(market_store, "get_market_store", lambda: _QuoteStore(None))
    monkeypatch.setattr(
        opportunity_routes,
        "_build_opportunities",
        lambda: {
            "categories": [
                {
                    "id": "trend",
                    "label": "趋势",
                    "opportunities": [_candidate()],
                }
            ]
        },
    )

    with pytest.raises(HTTPException) as exc:
        routes._candidate_pool("morning")

    assert exc.value.detail["blocking_reasons"] == ["realtime_snapshot_missing"]


def test_final_phase_times_are_exact() -> None:
    assert (routes._PHASES["morning_final"].hour, routes._PHASES["morning_final"].minute) == (9, 27)
    assert (routes._PHASES["afternoon_final"].hour, routes._PHASES["afternoon_final"].minute) == (14, 30)
    assert routes._AUTORUN_PHASES == ("morning_final", "afternoon_final")


def test_normalize_factors_never_labels_bearish_as_bullish() -> None:
    raw = {
        "signals": [
            {"id": "qlib158_roc20", "label": "20日动量", "rank_pct": 0.9, "status": "ok"},
            {"id": "qlib158_std60", "label": "60日波动", "rank_pct": 0.9, "status": "ok"},
            {"id": "alpha101_006", "label": "量价背离", "rank_pct": 0.2, "status": "ok"},
            {"id": "academic_rmw", "label": "低波质量", "rank_pct": 0.8, "status": "ok"},
        ]
    }

    result = routes._normalize_recommendation_factors(raw)

    assert result["status"] == "ok"
    assert all(row["direction"] == "bullish" for row in result["top_bullish"])
    assert all(row["direction"] == "bearish" for row in result["top_bearish"])
    assert {row["id"] for row in result["top_bullish"]} == {"qlib158_roc20", "academic_rmw"}
    assert {row["id"] for row in result["top_bearish"]} == {"qlib158_std60", "alpha101_006"}


def test_normalize_factors_is_limited_below_four_valid_signals() -> None:
    result = routes._normalize_recommendation_factors(
        {
            "signals": [
                {"id": "qlib158_roc20", "rank_pct": 0.8, "status": "ok"},
                {"id": "academic_smb", "rank_pct": 0.9, "status": "ok"},
            ]
        }
    )

    assert result["status"] == "limited"
    assert result["score"] == 0.5
    assert result["valid_signal_count"] == 1


def test_intraday_confirmation_penalizes_chasing_and_weak_close() -> None:
    item = _candidate() | {
        "change_pct": 7.5,
        "high": 10.8,
        "low": 9.8,
        "price": 10.0,
        "volume": 200.0,
        "daily_volume_avg_5": 100.0,
        "distance_ma20": 0.14,
    }

    result = routes._intraday_confirmation(item)

    assert result["score"] < 0.5
    assert "chase_risk" in result["adjustments"]
    assert "weak_intraday_close" in result["adjustments"]


def test_attach_intraday_history_metrics_uses_synthetic_current_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.data.market_data_service as market_data_service

    dates = pd.date_range("2026-06-15", periods=20, freq="B")
    history = pd.DataFrame(
        {
            "close": [10.0] * 20,
            "volume": [100.0] * 20,
        },
        index=dates,
    )
    monkeypatch.setattr(market_data_service, "latest_daily_bars", lambda symbol, days: history)

    item = routes._attach_intraday_history_metrics(
        _candidate() | {"price": 10.5, "volume": 60.0, "high": 10.6, "low": 9.9}
    )

    assert item["daily_volume_avg_5"] == 100.0
    assert item["synthetic_ma20"] > 10.0
    assert item["distance_ma20"] > 0
    assert item["market_context"]["daily_as_of"] == "2026-07-10"


def test_candidate_pool_attaches_intraday_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.opportunity_routes as opportunity_routes
    import src.data.market_data_service as market_data_service

    history = pd.DataFrame(
        {"close": [10.0] * 20, "volume": [100.0] * 20},
        index=pd.date_range("2026-06-15", periods=20, freq="B"),
    )
    monkeypatch.setattr(routes, "_assert_candidate_market_data_fresh", lambda: None)
    monkeypatch.setattr(
        routes,
        "_validated_realtime_quote",
        lambda item, slot: item
        | {"price": 10.5, "change_pct": 1.0, "high": 10.6, "low": 9.9, "volume": 60.0},
    )
    monkeypatch.setattr(market_data_service, "latest_daily_bars", lambda symbol, days: history)
    monkeypatch.setattr(
        opportunity_routes,
        "_build_opportunities",
        lambda: {
            "categories": [
                {"id": "trend", "label": "趋势", "opportunities": [_candidate()]},
            ]
        },
    )

    candidates = routes._candidate_pool("morning")

    assert candidates[0]["realtime_confirmation"]["score"] > 0.5


def test_candidate_pool_skips_invalid_quote_when_other_candidates_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.opportunity_routes as opportunity_routes

    monkeypatch.setattr(routes, "_assert_candidate_market_data_fresh", lambda: None)

    def validate(item: dict, slot: str) -> dict:
        if item["symbol"] == "600001.SH":
            raise HTTPException(
                status_code=503,
                detail={"code": "DATA_NOT_READY", "blocking_reasons": ["realtime_snapshot_missing"]},
            )
        return item | {"price": 10.5, "change_pct": 1.0}

    monkeypatch.setattr(routes, "_validated_realtime_quote", validate)
    monkeypatch.setattr(routes, "_attach_intraday_history_metrics", lambda item: item)
    monkeypatch.setattr(routes, "_intraday_confirmation", lambda item: {"score": 0.6})
    monkeypatch.setattr(
        opportunity_routes,
        "_build_opportunities",
        lambda: {
            "categories": [
                {
                    "id": "trend",
                    "label": "趋势",
                    "opportunities": [_candidate("600001.SH"), _candidate("600002.SH")],
                }
            ]
        },
    )

    candidates = routes._candidate_pool("morning")

    assert [item["symbol"] for item in candidates] == ["600002.SH"]


def test_factor_review_uses_recommendation_local_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.data.alpha_signals as alpha_signals

    raw = {
        "signals": [
            {"id": "qlib158_roc20", "label": "20日动量", "rank_pct": 0.9, "status": "ok"},
            {"id": "qlib158_std60", "label": "60日波动", "rank_pct": 0.9, "status": "ok"},
            {"id": "alpha101_006", "label": "量价背离", "rank_pct": 0.2, "status": "ok"},
            {"id": "academic_rmw", "label": "低波质量", "rank_pct": 0.8, "status": "ok"},
        ],
        "score": 0.99,
        "top_bullish": [
            {"id": "qlib158_std60", "label": "60日波动", "rank_pct": 0.9, "direction": "bearish"}
        ],
        "top_bearish": [],
        "peer_count": 20,
        "error": None,
    }
    monkeypatch.setattr(alpha_signals, "compute_alpha_signals", lambda symbol: raw)

    review = routes._factor_review(_candidate())

    assert review["score"] == 0.5
    assert review["valid_signal_count"] == 4
    assert {row["label"] for row in review["top_bullish"]} == {"20日动量", "低波质量"}
    assert all(row["direction"] == "bullish" for row in review["top_bullish"])


def _record(
    *,
    slot: str,
    category: str,
    score: float,
    change_pct: float,
    t1_return: float,
    ai_score: float = 0.6,
    factor_score: float = 0.6,
) -> dict:
    return {
        "slot": slot,
        "category": category,
        "strategy": category,
        "rank": 1,
        "score": score,
        "change_pct_at_pick": change_pct,
        "ai_review": {"score": ai_score},
        "factor_review": {"score": factor_score},
        "market_context": {"valid": True},
        "scoring": {"model_version": routes._RECOMMENDATION_MODEL_VERSION},
        "performance": {"t1": {"return_pct": t1_return}},
    }


def test_recommendation_attribution_groups_performance() -> None:
    records = [
        _record(slot="morning", category="breakout", score=0.77, change_pct=7.2, t1_return=-3.0, ai_score=0.8),
        _record(slot="morning", category="breakout", score=0.76, change_pct=6.4, t1_return=-1.0, ai_score=0.78),
        _record(slot="afternoon", category="trend", score=0.66, change_pct=1.2, t1_return=2.0, factor_score=0.7),
        _record(slot="afternoon", category="trend", score=0.64, change_pct=0.8, t1_return=1.0, factor_score=0.68),
    ]

    report = routes._recommendation_attribution(records, "t1")

    assert report["summary"]["completed_count"] == 4
    assert report["summary"]["win_rate"] == 50.0
    assert report["summary"]["avg_return"] == -0.25
    category_rows = {row["key"]: row for row in report["by_dimension"]["category"]}
    assert category_rows["breakout"]["avg_return"] == -2.0
    assert category_rows["trend"]["avg_return"] == 1.5


def test_recommendation_attribution_flags_weak_change_bucket() -> None:
    records = [
        _record(slot="morning", category="breakout", score=0.78, change_pct=6.2, t1_return=-2.0),
        _record(slot="morning", category="breakout", score=0.79, change_pct=7.0, t1_return=-3.0),
        _record(slot="morning", category="breakout", score=0.80, change_pct=8.5, t1_return=-1.0),
        _record(slot="afternoon", category="trend", score=0.68, change_pct=1.0, t1_return=1.5),
        _record(slot="afternoon", category="trend", score=0.69, change_pct=1.4, t1_return=2.0),
        _record(slot="afternoon", category="trend", score=0.70, change_pct=1.8, t1_return=1.0),
    ]

    report = routes._recommendation_attribution(records, "t1")

    change_rows = {row["key"]: row for row in report["by_dimension"]["change_bucket"]}
    assert change_rows[">=6%"]["avg_return"] == -2.0


def test_attribution_guardrails_penalize_morning_chase_breakout() -> None:
    item = {
        "category_id": "breakout",
        "change_pct": 7.0,
        "score": 0.82,
        "ai_review": {"score": 0.80},
        "factor_review": {"score": 0.62},
    }

    adjusted = routes._apply_attribution_guardrails(item, "morning")

    assert adjusted["score"] < 0.58
    assert "chase_high_penalty" in adjusted["attribution_adjustments"]
    assert "morning_hot_signal_penalty" in adjusted["attribution_adjustments"]


def test_attribution_guardrails_keep_moderate_trend() -> None:
    item = {
        "category_id": "trend",
        "change_pct": 1.8,
        "score": 0.62,
        "ai_review": {"score": 0.68},
        "factor_review": {"score": 0.69},
    }

    adjusted = routes._apply_attribution_guardrails(item, "afternoon")

    assert adjusted["score"] == 0.69
    assert "trend_prior" in adjusted["attribution_adjustments"]
    assert "moderate_intraday_move_prior" in adjusted["attribution_adjustments"]


def test_market_regime_from_closes_detects_risk_off() -> None:
    closes = [100 + i * 0.1 for i in range(40)] + [104 - i * 0.8 for i in range(20)]

    regime = routes._market_regime_from_closes(closes)

    assert regime["regime"] == "risk_off"


def test_market_regime_guardrail_penalizes_hot_signal_in_risk_off() -> None:
    item = {
        "category_id": "breakout",
        "change_pct": 7.0,
        "score": 0.82,
        "ai_review": {"score": 0.80},
        "factor_review": {"score": 0.62},
    }

    adjusted = routes._apply_attribution_guardrails(item, "morning", {"regime": "risk_off"})

    assert adjusted["score"] < 0.50
    assert "risk_off_hot_signal_penalty" in adjusted["attribution_adjustments"]
    assert "risk_off_chase_high_penalty" in adjusted["attribution_adjustments"]


def _scored(symbol: str, category: str, score: float) -> dict:
    return {
        "symbol": symbol,
        "category_id": category,
        "score": score,
        "deterministic_score": score,
        "eligible": True,
        "ai_review": {"score": 0.7, "decision": "recommend"},
    }


def _final_record(symbol: str, *, slot: str = "morning") -> dict:
    return {
        "symbol": symbol,
        "slot": slot,
        "target_date": "2026-07-14",
        "status": "final",
    }


def test_ai_cannot_rescue_candidate_below_deterministic_floor() -> None:
    item = _candidate() | {
        "score": 0.50,
        "realtime_confirmation": {"score": 0.50},
        "factor_review": {"score": 0.50},
        "ai_review": {"score": 0.99, "decision": "recommend"},
    }

    deterministic = routes._deterministic_score(item, {"regime": "neutral"})
    scored = routes._apply_ai_adjustment(deterministic)

    assert deterministic["eligible"] is False
    assert scored["eligible"] is False
    assert scored["score"] < 0.62
    assert scored["scoring"]["ai_adjustment"] <= 0.02


def test_candidate_without_exact_date_local_evidence_is_ineligible() -> None:
    item = _candidate() | {
        "score": 0.95,
        "realtime_confirmation": {"score": 0.95},
        "factor_review": {"score": 0.95, "status": "ok"},
        "local_evidence": {"score": 0.5, "status": "limited", "signals": []},
    }

    scored = routes._deterministic_score(item, {"regime": "risk_on"})

    assert scored["eligible"] is False
    assert "local" not in scored["scoring"]["evidence_sources"]


def test_selection_caps_each_category_at_three() -> None:
    candidates = [_scored(f"60000{i}.SH", "breakout", 0.90 - i / 100) for i in range(5)]
    candidates.append(_scored("000001.SZ", "trend", 0.70))

    selected = routes._select_final_candidates(
        candidates,
        routes._PHASES["morning_final"],
        5,
        [],
    )

    assert sum(item["category_id"] == "breakout" for item in selected) == 3
    assert any(item["category_id"] == "trend" for item in selected)
    assert len(selected) == 4


def test_afternoon_selection_caps_morning_repeats_at_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "_today_cst", lambda: "2026-07-14")
    morning_symbols = {"600001.SH", "600002.SH", "600003.SH"}
    existing = [_final_record(symbol) for symbol in morning_symbols]
    candidates = [_scored(symbol, "trend", 0.90) for symbol in sorted(morning_symbols)]
    candidates.extend(
        [
            _scored("000001.SZ", "oversold", 0.80),
            _scored("000002.SZ", "breakout", 0.79),
        ]
    )

    selected = routes._select_final_candidates(
        candidates,
        routes._PHASES["afternoon_final"],
        5,
        existing,
    )

    selected_symbols = {item["symbol"] for item in selected}
    assert len(selected_symbols & morning_symbols) == 2
    assert len(selected) == 4


def test_reviewed_candidates_rejects_low_deterministic_score_before_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_candidate_pool",
        lambda slot: [
            _candidate()
            | {
                "score": 0.50,
                "realtime_confirmation": {"score": 0.50},
            }
        ],
    )
    monkeypatch.setattr(routes, "_factor_review", lambda item: {"score": 0.50, "status": "ok"})
    monkeypatch.setattr(routes, "_current_market_regime", lambda: {"regime": "neutral"})
    ai_called = False

    def ai_review(candidates: list[dict], slot: str, limit: int) -> dict:
        nonlocal ai_called
        ai_called = True
        return {"600000.SH": {"score": 0.99, "decision": "recommend"}}

    monkeypatch.setattr(routes, "_ai_review_candidates", ai_review)

    with pytest.raises(HTTPException) as exc:
        routes._reviewed_candidates("morning", 5)

    assert exc.value.status_code == 503
    assert ai_called is False


def test_reviewed_candidates_apply_guardrails_in_production_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_candidate_pool",
        lambda slot: [
            _candidate()
            | {
                "score": 0.90,
                "category_id": "breakout",
                "change_pct": 7.0,
                "realtime_confirmation": {"score": 0.90},
            }
        ],
    )
    monkeypatch.setattr(routes, "_factor_review", lambda item: {"score": 0.90, "status": "ok"})
    monkeypatch.setattr(routes, "_current_market_regime", lambda: {"regime": "neutral"})
    monkeypatch.setattr(
        routes,
        "_ai_review_candidates",
        lambda candidates, slot, limit: {
            "600000.SH": {"score": 0.70, "decision": "recommend", "status": "ok"}
        },
    )

    reviewed = routes._reviewed_candidates("morning", 5)

    assert "morning_hot_signal_penalty" in reviewed[0]["attribution_adjustments"]
    assert "chase_high_penalty" in reviewed[0]["attribution_adjustments"]


def test_reviewed_candidates_keep_deterministic_pick_when_ai_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_candidate_pool",
        lambda slot: [
            _candidate()
            | {
                "score": 0.90,
                "realtime_confirmation": {"score": 0.90},
            }
        ],
    )
    monkeypatch.setattr(routes, "_factor_review", lambda item: {"score": 0.90, "status": "ok"})
    monkeypatch.setattr(routes, "_current_market_regime", lambda: {"regime": "neutral"})
    monkeypatch.setattr(routes, "_ai_review_candidates", lambda *args: (_ for _ in ()).throw(RuntimeError("AI down")))

    reviewed = routes._reviewed_candidates("afternoon", 5)

    assert reviewed[0]["eligible"] is True
    assert reviewed[0]["ai_review"]["status"] == "unavailable"


def _candidate(symbol: str = "600000.SH") -> dict:
    return {
        "symbol": symbol,
        "name": symbol,
        "price": 10.0,
        "change_pct": 1.0,
        "score": 0.72,
        "category_id": "trend",
        "reason": "trend setup",
        "ai_review": {"summary": "ok", "risk": "risk", "score": 0.7, "decision": "recommend"},
        "factor_review": {"summary": "factor ok", "score": 0.7},
        "local_evidence": {"status": "ok", "score": 0.7, "signals": []},
    }


def test_make_record_uses_explicit_phase_target_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "_now_cst", lambda: datetime(2026, 7, 2, 16, 0, tzinfo=routes._CST))

    record = routes._make_record(_candidate(), "post_close_base", "2026-07-03", 1, 2)

    assert record["id"] == "2026-07-03:post_close_base:v2:600000.SH"
    assert record["date"] == "2026-07-02"
    assert record["target_date"] == "2026-07-03"
    assert record["generation_phase"] == "post_close_base"
    assert record["status"] == "draft"
    assert record["version"] == 2


def test_make_record_persists_market_context_and_scoring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "_now_cst", lambda: datetime(2026, 7, 14, 9, 27, tzinfo=routes._CST))
    item = _candidate() | {
        "market_context": {
            "trade_date": "2026-07-14",
            "snapshot_at": "2026-07-14T09:27:00+08:00",
            "snapshot_age_seconds": 0.0,
            "quote_source": "test.realtime",
            "daily_as_of": "2026-07-13",
            "valid": True,
        },
        "scoring": {
            "base_score": 0.70,
            "realtime_score": 0.65,
            "factor_score": 0.60,
            "ai_adjustment": 0.01,
            "final_score": 0.70,
            "model_version": routes._RECOMMENDATION_MODEL_VERSION,
        },
    }

    record = routes._make_record(item, "morning_final", "2026-07-14", 1, 1)

    assert record["market_context"]["valid"] is True
    assert record["market_context"]["daily_as_of"] == "2026-07-13"
    assert record["scoring"]["model_version"] == routes._RECOMMENDATION_MODEL_VERSION
    assert record["scoring"]["final_score"] == 0.70


def test_promotion_status_requires_forward_evidence() -> None:
    records = [_record(slot="morning", category="trend", score=0.7, change_pct=1, t1_return=1.0)]

    status = routes._promotion_status(records, min_samples=3)

    assert status["decision"] == "insufficient_evidence"
    assert status["completed_samples"] == 1


def test_promotion_status_rejects_negative_expectancy() -> None:
    records = [
        _record(slot="morning", category="trend", score=0.7, change_pct=1, t1_return=value)
        for value in (-1.0, -0.5, 0.2)
    ]

    status = routes._promotion_status(records, min_samples=3)

    assert status["decision"] == "rejected"


def test_promotion_status_promotes_positive_expectancy() -> None:
    records = [
        _record(slot="afternoon", category="trend", score=0.7, change_pct=1, t1_return=value)
        for value in (1.0, 0.8, -0.1)
    ]

    status = routes._promotion_status(records, min_samples=3)

    assert status["decision"] == "eligible"
    assert status["t1_win_rate"] >= 50
    assert status["t1_median_return"] > 0


def test_promotion_status_rejects_positive_mean_with_bad_hit_rate() -> None:
    records = [
        _record(slot="afternoon", category="trend", score=0.7, change_pct=1, t1_return=value)
        for value in (10.0, -1.0, -1.0, -1.0)
    ]

    status = routes._promotion_status(records, min_samples=4)

    assert status["decision"] == "rejected"


def test_summary_excludes_legacy_and_invalid_records() -> None:
    valid = _record(
        slot="morning",
        category="trend",
        score=0.7,
        change_pct=1.0,
        t1_return=2.0,
    )
    invalid = {
        **_record(
            slot="morning",
            category="trend",
            score=0.7,
            change_pct=1.0,
            t1_return=-10.0,
        ),
        "market_context": {"valid": False},
    }
    legacy = {
        key: value
        for key, value in _record(
            slot="morning",
            category="trend",
            score=0.7,
            change_pct=1.0,
            t1_return=-20.0,
        ).items()
        if key not in {"market_context", "scoring"}
    }

    summary = routes._summary([valid, invalid, legacy])

    assert summary["count"] == 1
    assert summary["t1_count"] == 1
    assert summary["t1_avg_return"] == 2.0


def test_attribution_excludes_invalid_model_records() -> None:
    valid = _record(
        slot="morning",
        category="trend",
        score=0.7,
        change_pct=1.0,
        t1_return=2.0,
    )
    invalid = {
        **_record(
            slot="morning",
            category="breakout",
            score=0.9,
            change_pct=7.0,
            t1_return=-10.0,
        ),
        "market_context": {"valid": False},
    }

    report = routes._recommendation_attribution([valid, invalid], "t1")

    assert report["summary"]["count"] == 1
    assert report["summary"]["avg_return"] == 2.0


def test_generate_for_phase_versions_and_supersedes(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: list[dict] = []

    monkeypatch.setattr(routes, "_now_cst", lambda: datetime(2026, 7, 2, 16, 0, tzinfo=routes._CST))
    monkeypatch.setattr(routes, "_reviewed_candidates", lambda slot, limit: [_candidate("600000.SH")])
    monkeypatch.setattr(routes, "_load_records", lambda: list(storage))
    monkeypatch.setattr(routes, "_save_records", lambda records: storage.__setitem__(slice(None), records))

    first = routes._generate_for_phase("post_close_base", 1, target_date="2026-07-03")
    second = routes._generate_for_phase("post_close_base", 1, target_date="2026-07-03")

    assert first[0]["version"] == 1
    assert second[0]["version"] == 2
    old = next(record for record in storage if record["id"] == first[0]["id"])
    assert old["status"] == "superseded"

    final = routes._generate_for_phase("morning_final", 1, target_date="2026-07-03")
    draft = next(record for record in storage if record["id"] == second[0]["id"])
    assert final[0]["status"] == "final"
    assert draft["status"] == "superseded"


def test_autorun_keeps_unpromoted_model_in_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: list[dict] = []
    monkeypatch.setattr(routes, "_reviewed_candidates", lambda slot, limit: [_candidate()])
    monkeypatch.setattr(routes, "_load_records", lambda: list(storage))
    monkeypatch.setattr(routes, "_save_records", lambda records: storage.__setitem__(slice(None), records))

    generated = routes._generate_for_phase(
        "morning_final", 1, target_date="2026-07-14", shadow_until_promoted=True
    )

    assert generated[0]["status"] == "shadow"
    assert generated[0]["promotion_decision"] == "insufficient_evidence"


def test_autorun_publishes_after_shadow_evidence_is_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = [
        _record(slot="morning", category="trend", score=0.7, change_pct=1, t1_return=1.0)
        for _ in range(30)
    ]
    for record in storage:
        record["status"] = "shadow"
    monkeypatch.setattr(routes, "_reviewed_candidates", lambda slot, limit: [_candidate()])
    monkeypatch.setattr(routes, "_with_performance", lambda records: records)
    monkeypatch.setattr(routes, "_load_records", lambda: list(storage))
    monkeypatch.setattr(routes, "_save_records", lambda records: storage.__setitem__(slice(None), records))

    generated = routes._generate_for_phase(
        "morning_final", 1, target_date="2026-07-14", shadow_until_promoted=True
    )

    assert generated[0]["status"] == "final"
    assert generated[0]["promotion_decision"] == "eligible"


def test_generate_for_phase_applies_portfolio_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: list[dict] = []
    candidates = [
        _candidate(f"60000{idx}.SH") | _scored(f"60000{idx}.SH", "breakout", 0.90 - idx / 100)
        for idx in range(5)
    ]
    candidates.append(_candidate("000001.SZ") | _scored("000001.SZ", "trend", 0.70))

    monkeypatch.setattr(routes, "_now_cst", lambda: datetime(2026, 7, 14, 9, 27, tzinfo=routes._CST))
    monkeypatch.setattr(routes, "_today_cst", lambda: "2026-07-14")
    monkeypatch.setattr(routes, "_reviewed_candidates", lambda slot, limit: candidates)
    monkeypatch.setattr(routes, "_load_records", lambda: list(storage))
    monkeypatch.setattr(routes, "_save_records", lambda records: storage.__setitem__(slice(None), records))

    generated = routes._generate_for_phase("morning_final", 5, target_date="2026-07-14")

    assert len(generated) == 4
    assert sum(record["category"] == "breakout" for record in generated) == 3
    assert any(record["category"] == "trend" for record in generated)


def test_generate_final_supersedes_legacy_same_slot_final(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: list[dict] = [
        {
            "id": "2026-07-03:morning:v1:600001.SH",
            "date": "2026-07-03",
            "target_date": "2026-07-03",
            "slot": "morning",
            "generation_phase": "morning",
            "status": "final",
            "version": 1,
            "symbol": "600001.SH",
            "rank": 1,
            "created_at": "2026-07-03T09:20:00+08:00",
        }
    ]

    monkeypatch.setattr(routes, "_now_cst", lambda: datetime(2026, 7, 3, 9, 24, tzinfo=routes._CST))
    monkeypatch.setattr(routes, "_reviewed_candidates", lambda slot, limit: [_candidate("600000.SH")])
    monkeypatch.setattr(routes, "_load_records", lambda: list(storage))
    monkeypatch.setattr(routes, "_save_records", lambda records: storage.__setitem__(slice(None), records))

    routes._generate_for_phase("morning_final", 1, target_date="2026-07-03")

    legacy = next(record for record in storage if record["id"] == "2026-07-03:morning:v1:600001.SH")
    assert legacy["status"] == "superseded"


def test_cap_latest_final_per_slot_keeps_latest_batch_only() -> None:
    old_batch = [
        {
            "id": f"old-{idx}",
            "target_date": "2026-07-03",
            "date": "2026-07-03",
            "slot": "morning",
            "generation_phase": "morning",
            "status": "final",
            "version": 1,
            "rank": idx,
            "created_at": f"2026-07-03T09:20:0{idx}+08:00",
        }
        for idx in range(1, 6)
    ]
    new_batch = [
        {
            "id": f"new-{idx}",
            "target_date": "2026-07-03",
            "date": "2026-07-03",
            "slot": "morning",
            "generation_phase": "morning_final",
            "status": "final",
            "version": 1,
            "rank": idx,
            "created_at": f"2026-07-03T09:24:0{idx}+08:00",
        }
        for idx in range(1, 6)
    ]

    visible = routes._cap_latest_final_per_slot(old_batch + new_batch)

    assert [record["id"] for record in visible] == [f"new-{idx}" for idx in range(1, 6)]
