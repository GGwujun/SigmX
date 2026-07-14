# Daily Recommendation Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 9:27 and 14:30 daily recommendation batches fail closed on invalid market snapshots and rank candidates with recommendation-local, auditable evidence.

**Architecture:** Keep shared opportunity and Alpha modules read-only. Add a strict adapter inside `daily_recommendation_routes.py` that validates current quotes, computes intraday confirmation and recommendation-local factors, produces deterministic scores, constrains the final portfolio, and persists an evidence envelope.

**Tech Stack:** Python 3.11+, FastAPI, SQLite-backed MarketStore, pandas, pytest.

## Global Constraints

- Work directly on the current `main` branch; do not create a branch or worktree.
- Modify only `agent/src/api/daily_recommendation_routes.py` and `agent/tests/test_daily_recommendation_routes.py` for functional behavior.
- Do not modify opportunity scanning, shared Alpha, synchronization, dashboards, positions, or other pages.
- Automatic generation runs only for `morning_final` at 09:27 and `afternoon_final` at 14:30.
- Missing or stale realtime data must block generation; never fall back to a daily close.
- Use TDD for every behavior change.

---

### Task 1: Strict slot quote context and two-point scheduler

**Files:**
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Produces: `_validated_realtime_quote(item: dict[str, Any], slot: str, now: datetime | None = None) -> dict[str, Any]`
- Produces: `_quote_age_seconds(snapshot_at: str, now: datetime) -> float`
- Changes: `_candidate_pool(slot)` excludes invalid quotes and raises structured `DATA_NOT_READY` when no candidates remain.

- [ ] **Step 1: Write failing quote-gate and schedule tests**

```python
def test_validated_realtime_quote_rejects_missing_snapshot(monkeypatch):
    monkeypatch.setattr(market_store, "get_market_store", lambda: _FakeStore(quote=None))
    with pytest.raises(HTTPException) as exc:
        routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))
    assert exc.value.detail["blocking_reasons"] == ["realtime_snapshot_missing"]

def test_validated_realtime_quote_rejects_stale_snapshot(monkeypatch):
    quote = _quote(snapshot_at="2026-07-14T09:20:00+08:00")
    monkeypatch.setattr(market_store, "get_market_store", lambda: _FakeStore(quote=quote))
    with pytest.raises(HTTPException) as exc:
        routes._validated_realtime_quote(_candidate(), "morning", _at(9, 27))
    assert "realtime_snapshot_stale" in exc.value.detail["blocking_reasons"]

def test_final_phase_times_are_exact():
    assert (routes._PHASES["morning_final"].hour, routes._PHASES["morning_final"].minute) == (9, 27)
    assert (routes._PHASES["afternoon_final"].hour, routes._PHASES["afternoon_final"].minute) == (14, 30)
    assert routes._AUTORUN_PHASES == ("morning_final", "afternoon_final")
```

- [ ] **Step 2: Verify the new tests fail**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -k "validated_realtime_quote or final_phase_times" -q`

Expected: FAIL because `_validated_realtime_quote` and `_AUTORUN_PHASES` do not exist and phase minutes are 24/20.

- [ ] **Step 3: Implement the strict adapter and scheduler constants**

```python
_MAX_QUOTE_AGE_SECONDS = 180
_AUTORUN_PHASES = ("morning_final", "afternoon_final")

def _validated_realtime_quote(item, slot, now=None):
    current = now or _now_cst()
    quote = get_market_store().get_latest_realtime_quote(normalize_code(item["symbol"]), current.date().isoformat())
    reasons = _validate_quote(quote, current)
    if reasons:
        raise HTTPException(status_code=503, detail={
            "code": "DATA_NOT_READY", "slot": slot,
            "trade_date": current.date().isoformat(), "blocking_reasons": reasons,
        })
    return {**item, "price": float(quote["price"]), "change_pct": float(quote["rise_rate"]),
            "market_context": _market_context_from_quote(quote, current)}
```

Update the scheduler loop to build checks from `_AUTORUN_PHASES` only.

- [ ] **Step 4: Run the Task 1 tests**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -k "realtime or final_phase_times or candidate_market_data" -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add agent/src/api/daily_recommendation_routes.py agent/tests/test_daily_recommendation_routes.py
git commit -m "fix(recommendations): require fresh slot quotes"
```

### Task 2: Recommendation-local intraday confirmation and factor normalization

**Files:**
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Produces: `_attach_intraday_history_metrics(item: dict[str, Any]) -> dict[str, Any]`
- Produces: `_intraday_confirmation(item: dict[str, Any]) -> dict[str, Any]`
- Produces: `_normalize_recommendation_factors(raw: dict[str, Any]) -> dict[str, Any]`
- Changes: `_factor_review` consumes normalized signals instead of shared composite/top lists.

- [ ] **Step 1: Write failing normalization and intraday tests**

```python
def test_normalize_factors_never_labels_bearish_as_bullish():
    raw = {"signals": [
        {"id": "qlib158_roc20", "rank_pct": 0.9, "status": "ok"},
        {"id": "qlib158_std60", "rank_pct": 0.9, "status": "ok"},
        {"id": "alpha101_006", "rank_pct": 0.2, "status": "ok"},
        {"id": "academic_rmw", "rank_pct": 0.8, "status": "ok"},
    ]}
    result = routes._normalize_recommendation_factors(raw)
    assert all(row["direction"] == "bullish" for row in result["top_bullish"])
    assert all(row["direction"] == "bearish" for row in result["top_bearish"])

def test_normalize_factors_is_limited_below_four_valid_signals():
    result = routes._normalize_recommendation_factors({"signals": [
        {"id": "qlib158_roc20", "rank_pct": 0.8, "status": "ok"},
    ]})
    assert result["status"] == "limited"
    assert result["score"] == 0.5

def test_intraday_confirmation_penalizes_chasing_and_weak_close():
    item = _candidate() | {"change_pct": 7.5, "high": 10.8, "low": 9.8, "price": 10.0,
                           "volume": 200, "daily_volume_avg_5": 100}
    result = routes._intraday_confirmation(item)
    assert result["score"] < 0.5

def test_attach_intraday_history_metrics_uses_synthetic_current_bar(monkeypatch):
    history = _daily_frame(closes=[10.0] * 20, volumes=[100.0] * 20)
    monkeypatch.setattr(market_data_service, "latest_daily_bars", lambda symbol, days: history)
    item = routes._attach_intraday_history_metrics(
        _candidate() | {"price": 10.5, "volume": 60.0, "high": 10.6, "low": 9.9}
    )
    assert item["daily_volume_avg_5"] == 100.0
    assert item["synthetic_ma20"] > 10.0
    assert item["distance_ma20"] > 0
```

- [ ] **Step 2: Verify the Task 2 tests fail**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -k "normalize_factors or intraday_confirmation" -q`

Expected: FAIL because the functions do not exist.

- [ ] **Step 3: Implement explicit recommendation polarity and confirmation**

```python
_RECOMMENDATION_FACTOR_POLARITY = {
    "alpha101_006": 1, "alpha101_013": 1, "alpha101_043": 1,
    "qlib158_roc20": 1, "alpha101_050": 1, "alpha101_044": 1,
    "academic_rmw": 1, "qlib158_std60": -1, "qlib158_ma5": -1,
}

def _normalize_recommendation_factors(raw):
    normalized = []
    for signal in raw.get("signals", []):
        polarity = _RECOMMENDATION_FACTOR_POLARITY.get(str(signal.get("id")))
        if polarity is None or signal.get("status") != "ok":
            continue
        rank_pct = max(0.01, min(0.99, float(signal.get("rank_pct", 0.5))))
        directional_rank = rank_pct if polarity > 0 else 1.0 - rank_pct
        direction = "bullish" if directional_rank >= 0.7 else "bearish" if directional_rank <= 0.3 else "neutral"
        contribution = 0.5 if direction == "neutral" else directional_rank
        normalized.append({**signal, "direction": direction, "contribution": contribution})
    if len(normalized) < 4:
        return {"status": "limited", "score": 0.5, "top_bullish": [], "top_bearish": [], "signals": normalized}
    bullish = sorted((s for s in normalized if s["direction"] == "bullish"), key=lambda s: s["contribution"], reverse=True)
    bearish = sorted((s for s in normalized if s["direction"] == "bearish"), key=lambda s: s["contribution"])
    return {"status": "ok", "score": sum(s["contribution"] for s in normalized) / len(normalized),
            "top_bullish": bullish[:3], "top_bearish": bearish[:3], "signals": normalized}

def _intraday_confirmation(item):
    price, high, low = float(item["price"]), float(item["high"]), float(item["low"])
    change = float(item.get("change_pct", 0))
    volume = float(item.get("volume", 0))
    avg_volume = float(item.get("daily_volume_avg_5", 0))
    position = (price - low) / (high - low) if high > low else 0.5
    volume_ratio = volume / avg_volume if avg_volume > 0 else 0.0
    score = 0.5 + (position - 0.5) * 0.2
    if 0 <= change < 3:
        score += 0.08
    if change >= 6:
        score -= 0.20
    if volume_ratio > 3:
        score -= 0.08
    return {"score": max(0.01, min(0.99, score)), "position": position, "volume_ratio": volume_ratio}

def _attach_intraday_history_metrics(item):
    history = latest_daily_bars(str(item["symbol"]), days=30).sort_index()
    closes = [float(value) for value in history["close"].tail(19)] + [float(item["price"])]
    volumes = [float(value) for value in history["volume"].tail(5)]
    ma20 = sum(closes) / len(closes)
    avg_volume = sum(volumes) / len(volumes)
    return {**item, "synthetic_ma20": ma20, "distance_ma20": float(item["price"]) / ma20 - 1.0,
            "daily_volume_avg_5": avg_volume}
```

The implementation must use concrete arithmetic from the design and must not call or modify shared score aggregation.

- [ ] **Step 4: Run Task 2 and full recommendation tests**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add agent/src/api/daily_recommendation_routes.py agent/tests/test_daily_recommendation_routes.py
git commit -m "fix(recommendations): normalize local factor evidence"
```

### Task 3: Deterministic scoring, constrained AI, and portfolio selection

**Files:**
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Produces: `_deterministic_score(item: dict[str, Any], regime: dict[str, Any]) -> dict[str, Any]`
- Produces: `_select_final_candidates(candidates, phase, limit, existing_records) -> list[dict[str, Any]]`
- Changes: `_reviewed_candidates` gates on deterministic score before AI adjustment.

- [ ] **Step 1: Write failing score and selection tests**

```python
def test_ai_cannot_rescue_candidate_below_deterministic_floor():
    item = _candidate() | {"base_score": 0.50, "realtime_confirmation": {"score": 0.50},
                           "factor_review": {"score": 0.50},
                           "ai_review": {"score": 0.99, "decision": "recommend"}}
    scored = routes._apply_ai_adjustment(routes._deterministic_score(item, {"regime": "neutral"}))
    assert scored["eligible"] is False

def test_selection_caps_each_category_at_three():
    candidates = [_scored(f"60000{i}.SH", "breakout", 0.9 - i / 100) for i in range(5)]
    candidates += [_scored("000001.SZ", "trend", 0.70)]
    selected = routes._select_final_candidates(candidates, routes._PHASES["morning_final"], 5, [])
    assert sum(x["category_id"] == "breakout" for x in selected) == 3

def test_afternoon_selection_caps_morning_repeats_at_two():
    existing = [_final_record(symbol) for symbol in ("600001.SH", "600002.SH", "600003.SH")]
    candidates = [_scored(symbol, "trend", 0.9) for symbol in ("600001.SH", "600002.SH", "600003.SH")]
    candidates += [_scored("000001.SZ", "trend", 0.8), _scored("000002.SZ", "trend", 0.79)]
    selected = routes._select_final_candidates(candidates, routes._PHASES["afternoon_final"], 5, existing)
    assert len({x["symbol"] for x in selected} & {"600001.SH", "600002.SH", "600003.SH"}) == 2
```

- [ ] **Step 2: Verify the Task 3 tests fail**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -k "deterministic or selection or ai_cannot" -q`

Expected: FAIL because the score and selection interfaces do not exist.

- [ ] **Step 3: Implement deterministic scoring and constraints**

```python
score = base * 0.45 + realtime * 0.30 + factor * 0.20 + regime_adjustment
eligible = score >= 0.62
ai_adjustment = max(-0.02, min(0.02, (ai_score - 0.5) * 0.04))
```

Apply AI only after `eligible` is fixed. Select in score order with category cap 3 and afternoon repeat cap 2; return fewer than five when constraints leave fewer eligible candidates.

- [ ] **Step 4: Run the full recommendation test file**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add agent/src/api/daily_recommendation_routes.py agent/tests/test_daily_recommendation_routes.py
git commit -m "refactor(recommendations): make scoring deterministic"
```

### Task 4: Evidence persistence and valid-only evaluation

**Files:**
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Produces: `_is_valid_model_record(record: dict[str, Any]) -> bool`
- Changes: `_make_record` persists `market_context` and `scoring`.
- Changes: summary, backtest, and attribution calculations exclude legacy/invalid records by default.

- [ ] **Step 1: Write failing evidence and evaluation tests**

```python
def test_make_record_persists_market_context_and_scoring(monkeypatch):
    item = _candidate() | {"market_context": {"valid": True, "snapshot_at": "2026-07-14T09:27:00+08:00"},
                           "scoring": {"model_version": "daily-v2", "final_score": 0.72}}
    record = routes._make_record(item, "morning_final", "2026-07-14", 1, 1)
    assert record["market_context"]["valid"] is True
    assert record["scoring"]["model_version"] == "daily-v2"

def test_summary_excludes_legacy_and_invalid_records():
    valid = _record_with_performance(valid=True, return_pct=2.0)
    invalid = _record_with_performance(valid=False, return_pct=-10.0)
    legacy = _record_with_performance(valid=None, return_pct=-20.0)
    assert routes._summary([valid, invalid, legacy])["t1_avg_return"] == 2.0
```

- [ ] **Step 2: Verify the Task 4 tests fail**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py -k "persists_market_context or excludes_legacy" -q`

Expected: FAIL because evidence fields are not persisted and summaries include legacy records.

- [ ] **Step 3: Persist evidence and filter evaluation inputs**

```python
def _is_valid_model_record(record):
    context = record.get("market_context") or {}
    scoring = record.get("scoring") or {}
    return context.get("valid") is True and scoring.get("model_version") == "daily-v2"
```

Keep legacy records visible in list APIs but exclude them from aggregate performance statistics.

- [ ] **Step 4: Run all directly related tests**

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py agent/tests/test_opportunity_routes.py -q`

Expected: PASS, demonstrating recommendation changes did not alter shared opportunity behavior.

- [ ] **Step 5: Commit Task 4**

```bash
git add agent/src/api/daily_recommendation_routes.py agent/tests/test_daily_recommendation_routes.py
git commit -m "feat(recommendations): persist auditable evidence"
```

### Task 5: Scope and regression verification

**Files:**
- Verify only: `agent/src/api/daily_recommendation_routes.py`
- Verify only: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Consumes all prior task interfaces.
- Produces a verified, scoped implementation.

- [ ] **Step 1: Verify changed functional files are in scope**

Run: `git diff --name-only 985eb89..HEAD`

Expected functional files: only the daily recommendation route and its dedicated test. Plan documentation may also appear.

- [ ] **Step 2: Run syntax and focused tests**

Run: `python -m py_compile agent/src/api/daily_recommendation_routes.py`

Run: `python -m pytest agent/tests/test_daily_recommendation_routes.py agent/tests/test_opportunity_routes.py -q`

Expected: exit code 0 with zero failures.

- [ ] **Step 3: Run diff quality checks**

Run: `git diff --check 985eb89..HEAD`

Expected: no output and exit code 0.

- [ ] **Step 4: Inspect final status and commit history**

Run: `git status -sb && git log --oneline 985eb89..HEAD`

Expected: clean working tree and four implementation commits.
