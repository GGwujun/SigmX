from __future__ import annotations

from datetime import datetime

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
