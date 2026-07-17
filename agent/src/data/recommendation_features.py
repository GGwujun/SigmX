"""Point-in-time, locally reproducible evidence for daily recommendations."""

from __future__ import annotations

import os
from typing import Any

from src.data.sector_matching import match_sector_row


_HISTORY_BARS = int(os.getenv("RECOMMENDATION_HISTORY_BARS", "60"))
_HISTORY_MIN_CODES = int(os.getenv("RECOMMENDATION_HISTORY_MIN_CODES", "3000"))
_HISTORY_MIN_COVERAGE = float(os.getenv("RECOMMENDATION_HISTORY_MIN_COVERAGE", "0.90"))


def history_readiness(
    store,
    *,
    min_bars: int = _HISTORY_BARS,
    min_codes: int = _HISTORY_MIN_CODES,
    min_coverage: float = _HISTORY_MIN_COVERAGE,
) -> dict[str, Any]:
    metrics = dict(store.get_recommendation_history_coverage(min_bars))
    active = int(metrics.get("active_codes") or 0)
    covered = int(metrics.get("covered_codes") or 0)
    coverage = float(metrics.get("coverage") or 0.0)
    reasons: list[str] = []
    if active < min_codes:
        reasons.append("active_universe_below_minimum")
    if covered < min_codes:
        reasons.append("history_covered_codes_below_minimum")
    if coverage < min_coverage:
        reasons.append("history_coverage_below_threshold")
    return {
        "ready": not reasons,
        "active_codes": active,
        "covered_codes": covered,
        "coverage": round(coverage, 4),
        "min_bars": min_bars,
        "min_codes": min_codes,
        "min_coverage": min_coverage,
        "blocking_reasons": reasons,
    }


def _short_code(value: str) -> str:
    text = str(value or "").upper()
    digits = "".join(char for char in text if char.isdigit())
    return digits[-6:]


def _dataset_available(store, dataset: str, trade_date: str, require_published: bool) -> bool:
    return not require_published or bool(store.get_data_readiness(dataset, trade_date).ready)


def _read_exact_date_rows(
    store,
    table: str,
    trade_date: str,
    columns: str,
    *,
    verify_max: bool = True,
) -> list:
    """Read rows for ``trade_date`` and optionally verify the table's max date.

    A readiness record can be VERIFIED while the table still holds yesterday's
    rows (a half-applied upsert); a bare ``WHERE trade_date = ?`` would then
    silently return nothing or stale data. When ``verify_max`` is set (the
    default, used for the current-day read) we confirm the requested date is the
    max present before trusting the result.

    ``verify_max`` must be False for prior-day fallback reads: a table that
    already holds today's rows legitimately has MAX(trade_date) == today, which
    must NOT invalidate a correct yesterday read.
    """
    rows = store._conn.execute(
        f"SELECT {columns} FROM {table} WHERE trade_date = ?", (trade_date,)
    ).fetchall()
    if not rows or not verify_max:
        return list(rows)
    latest = store._conn.execute(
        f"SELECT MAX(trade_date) AS d FROM {table}"
    ).fetchone()
    if latest and str(latest["d"] or "")[:10] != trade_date[:10]:
        return []
    return list(rows)


def _read_with_fallback(
    store,
    dataset: str,
    table: str,
    trade_date: str,
    columns: str,
    *,
    require_published: bool,
) -> tuple[list, str, bool]:
    """Read a dataset for ``trade_date``, falling back to the prior trading day.

    Some inputs (e.g. ``fund_flow_daily``) are only produced by the post-close
    sync, so at intraday recommendation times the current day is never ready.
    Rather than dropping the signal entirely, we fall back to the most recent
    trading day and mark the evidence ``is_fallback`` so scoring can down-weight
    it.  Returns ``(rows, as_of, is_fallback)``.
    """
    from src.data.trade_calendar import previous_trading_day

    if _dataset_available(store, dataset, trade_date, require_published):
        rows = _read_exact_date_rows(store, table, trade_date, columns)
        if rows:
            return rows, trade_date, False
    fallback_date = previous_trading_day(trade_date)
    if _dataset_available(store, dataset, fallback_date, require_published):
        # verify_max=False: the table legitimately holds today's rows on top of
        # yesterday's, which must not invalidate a correct fallback read.
        rows = _read_exact_date_rows(store, table, fallback_date, columns, verify_max=False)
        if rows:
            return rows, fallback_date, True
    return [], trade_date, False


def load_recommendation_features(
    store,
    codes: list[str],
    trade_date: str,
    *,
    require_published: bool = True,
) -> dict[str, dict[str, Any]]:
    """Build an exact-date evidence snapshot; unavailable datasets contribute nothing."""
    by_short = {_short_code(code): str(code).upper() for code in codes}
    result = {
        code: {"status": "limited", "score": 0.5, "signals": [], "as_of": trade_date}
        for code in by_short.values()
    }

    def add(raw_code: str, dataset: str, contribution: float, detail: dict[str, Any]) -> None:
        code = by_short.get(_short_code(raw_code))
        if not code:
            return
        result[code]["signals"].append(
            {"dataset": dataset, "contribution": round(contribution, 3), **detail}
        )

    if _dataset_available(store, "capital_rank", trade_date, require_published):
        rows = _read_exact_date_rows(
            store, "stock_capital_rank", trade_date, "code, rank_type, main_net, change_pct"
        )
        for row in rows:
            value = float(row["main_net"] or 0)
            add(row["code"], "capital_rank", 0.14 if value > 0 else -0.12 if value < 0 else 0.0, {
                "rank_type": row["rank_type"], "main_net": value
            })

    if _dataset_available(store, "hot_list", trade_date, require_published):
        rows = _read_exact_date_rows(
            store, "hot_list", trade_date, "code, rank, hot_value, source"
        )
        for row in rows:
            rank = int(row["rank"] or 100)
            add(row["code"], "hot_list", max(0.03, 0.16 * (1 - min(rank, 100) / 100)), {
                "rank": rank, "source": row["source"]
            })

    if _dataset_available(store, "ths_hot", trade_date, require_published):
        rows = _read_exact_date_rows(
            store, "ths_hot_reason", trade_date, "code, reason"
        )
        for row in rows:
            add(row["code"], "ths_hot", 0.10, {"reason": row["reason"]})

    ff_rows, ff_as_of, ff_fallback = _read_with_fallback(
        store,
        "fund_flow_daily",
        "fund_flow_daily",
        trade_date,
        "code, main_net, net_amount, source",
        require_published=require_published,
    )
    for row in ff_rows:
        value = float(row["main_net"] or row["net_amount"] or 0)
        add(row["code"], "fund_flow_daily", 0.10 if value > 0 else -0.10 if value < 0 else 0.0, {
            "main_net": value,
            "source": row["source"],
            "as_of": ff_as_of,
            "is_fallback": ff_fallback,
        })

    if _dataset_available(store, "sector_capital", trade_date, require_published):
        masters = store._conn.execute(
            "SELECT code, industry FROM security_master WHERE code IN (%s)"
            % ",".join("?" for _ in by_short),
            tuple(by_short.values()),
        ).fetchall() if by_short else []
        sector_rows = [
            dict(row)
            for row in _read_exact_date_rows(
                store, "sector_capital_flow", trade_date, "sector, main_net, change_pct"
            )
        ]
        for master in masters:
            row = match_sector_row(master["industry"], sector_rows)
            if row is None:
                continue
            value = float(row["main_net"] or 0)
            add(master["code"], "sector_capital", 0.08 if value > 0 else -0.08 if value < 0 else 0.0, {
                "sector": row["sector"], "main_net": value, "change_pct": row["change_pct"]
            })

    if _dataset_available(store, "zt_pool", trade_date, require_published):
        rows = _read_exact_date_rows(
            store, "zt_pool", trade_date, "code, pct, limit_days, break_times"
        )
        for row in rows:
            add(row["code"], "zt_pool", -0.12, {
                "pct": row["pct"], "limit_days": row["limit_days"],
                "break_times": row["break_times"], "reason": "limit_up_chase_risk",
            })

    breadth_signal: dict[str, Any] | None = None
    if _dataset_available(store, "market_breadth", trade_date, require_published):
        rows = _read_exact_date_rows(
            store,
            "market_breadth_snapshot",
            trade_date,
            "total, advancers, decliners, limit_up, limit_down, source",
        )
        row = rows[0] if rows else None
        if row:
            total = max(1, int(row["total"] or 0))
            ratio = (int(row["advancers"] or 0) - int(row["decliners"] or 0)) / total
            breadth_signal = {
                "dataset": "market_breadth",
                "contribution": round(max(-0.08, min(0.08, ratio * 0.16)), 3),
                "advancers": row["advancers"], "decliners": row["decliners"],
                "limit_up": row["limit_up"], "limit_down": row["limit_down"],
                "source": row["source"],
            }

    for feature in result.values():
        symbol_signals = list(feature["signals"])
        if breadth_signal:
            feature["signals"].append(dict(breadth_signal))
        # Duplicate provider/ranking rows from one dataset count only once.
        grouped: dict[str, list[float]] = {}
        for signal in feature["signals"]:
            grouped.setdefault(str(signal["dataset"]), []).append(float(signal["contribution"]))
        contribution = sum(
            max(values) if max(values) > 0 else min(values)
            for values in grouped.values()
        )
        feature["score"] = round(max(0.01, min(0.99, 0.5 + contribution)), 3)
        # Three-state evidence health. A missing market_breadth snapshot must
        # NOT collapse every symbol to "limited" — breadth is one neutral
        # market-wide row, not per-symbol evidence.  Status is driven by how
        # many of the per-symbol datasets actually fired.
        unique_symbol_sources = {
            str(signal["dataset"]) for signal in symbol_signals
        }
        if not symbol_signals:
            feature["status"] = "limited"
        elif len(unique_symbol_sources) >= 2:
            feature["status"] = "ok"
        else:
            feature["status"] = "partial"
        feature["evidence_count"] = len(feature["signals"])
        feature["breadth_available"] = bool(breadth_signal)
    return result
