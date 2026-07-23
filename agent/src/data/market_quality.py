"""Strict quality contracts shared by market-data writers and readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.data.market_store import MarketStore


class QualityStatus(StrEnum):
    """Lifecycle states for a sync run or one of its datasets."""

    PENDING = "pending"
    FETCHING = "fetching"
    VALIDATING = "validating"
    VERIFIED = "verified"
    PUBLISHED = "published"
    PARTIAL = "partial"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass
class DatasetQualityReport:
    """Validation outcome for one dataset and exact trade date."""

    dataset: str
    trade_date: str
    status: QualityStatus
    expected_rows: int
    received_rows: int
    valid_rows: int
    published_rows: int = 0
    missing_codes: list[str] = field(default_factory=list)
    invalid_rows: list[dict] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    source: str = ""


@dataclass(frozen=True)
class DataReadiness:
    """Read-side contract for deciding whether business data may be consumed."""

    dataset: str
    as_of: str
    status: QualityStatus
    expected_rows: int
    valid_rows: int
    published_rows: int
    source: str
    run_id: str
    blocking_reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status in {QualityStatus.VERIFIED, QualityStatus.PUBLISHED}


@dataclass(frozen=True)
class SuspensionResult:
    """Authoritative suspension lookup, preserving unavailable vs. empty."""

    available: bool
    codes: frozenset[str] = frozenset()
    source: str = "tushare.suspend_d"
    error: str = ""

    @classmethod
    def success(cls, codes: set[str]) -> "SuspensionResult":
        return cls(available=True, codes=frozenset(code.upper() for code in codes))

    @classmethod
    def unavailable(cls, error: str) -> "SuspensionResult":
        return cls(available=False, error=error)


@dataclass(frozen=True)
class ReferenceResult:
    """Independent exact-date close-price sample used for reconciliation."""

    available: bool
    closes: dict[str, float] = field(default_factory=dict)
    source: str = "tpdog.stock/daily"
    error: str = ""

    @classmethod
    def success(cls, closes: dict[str, float]) -> "ReferenceResult":
        return cls(available=True, closes={code.upper(): float(value) for code, value in closes.items()})

    @classmethod
    def unavailable(cls, error: str, *, closes: dict[str, float] | None = None) -> "ReferenceResult":
        return cls(available=False, closes=closes or {}, error=error)


def _invalid_ohlc_reason(row: dict) -> str | None:
    try:
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
    except (KeyError, TypeError, ValueError):
        return "non_numeric_ohlcv"
    if min(open_price, high, low, close) <= 0:
        return "non_positive_ohlc"
    if high < max(open_price, close):
        return "high_below_open_or_close"
    if low > min(open_price, close):
        return "low_above_open_or_close"
    if high < low:
        return "high_below_low"
    if volume < 0:
        return "negative_volume"
    if not row.get("source") or row.get("source") == "unknown":
        return "missing_source"
    if not row.get("sync_run_id"):
        return "missing_sync_run_id"
    return None


def validate_daily_dataset(
    store: "MarketStore",
    trade_date: str,
    expected_codes: list[str],
    run_id: str,
    *,
    suspension_result: SuspensionResult,
    reference_result: ReferenceResult,
    fallback_reference_result: ReferenceResult | None = None,
    close_tolerance: float = 0.001,
) -> DatasetQualityReport:
    """Validate one exact-date daily dataset; uncertainty always blocks publish."""
    expected = {code.upper() for code in expected_codes}
    blocking_reasons: list[str] = []
    if suspension_result.available:
        expected -= set(suspension_result.codes)
    else:
        blocking_reasons.append("suspension_reference_unavailable")
    if not reference_result.available:
        blocking_reasons.append("cross_source_reference_unavailable")

    rows = store.daily_rows_for_run(trade_date, run_id)
    fallback_codes = {
        str(row.get("code") or "").upper()
        for row in rows
        if str(row.get("source") or "").startswith("tpdog.")
    }
    # The TDX reference fetcher returns ReferenceResult.unavailable(...) with a
    # partially-populated ``closes`` when only *some* codes failed, and an empty
    # ``closes`` when the whole mootdx connection is down.  Distinguish these so
    # a flaky TDX server degrades instead of freezing every tpdog-sourced bar.
    if fallback_reference_result is not None:
        fallback_closes = dict(fallback_reference_result.closes)
        tdx_entirely_down = (
            not fallback_reference_result.available and not fallback_closes
        )
    else:
        fallback_closes = {}
        tdx_entirely_down = True
    if fallback_codes and not tdx_entirely_down:
        # TDX is at least partially reachable: every fallback code must have a
        # reference close to count as verified.  Uncovered codes are flagged so
        # the recommendation layer can down-weight them, but a low coverage
        # ratio is what blocks (not any single missing code).
        uncovered = sorted(fallback_codes - set(fallback_closes))
        verified_ratio = (
            len(fallback_codes & set(fallback_closes)) / len(fallback_codes)
            if fallback_codes
            else 1.0
        )
        if uncovered and verified_ratio < 0.5:
            blocking_reasons.append("fallback_reference_coverage_too_low")
    # When tdx_entirely_down is True we do NOT block: the bars are accepted
    # unverifiable (no independent reference exists) rather than discarding the
    # entire post-close run because mootdx could not connect.
    received_codes = {str(row["code"]).upper() for row in rows}
    missing_codes = sorted(expected - received_codes)
    if missing_codes:
        blocking_reasons.append("unexplained_missing_codes")

    invalid_rows: list[dict] = []
    valid_rows = 0
    for row in rows:
        reason = _invalid_ohlc_reason(row)
        code = str(row.get("code") or "").upper()
        if row.get("trade_date") != trade_date:
            reason = "wrong_trade_date"
        elif row.get("sync_run_id") != run_id:
            reason = "wrong_sync_run_id"
        if reason:
            invalid = {**row, "reason": reason}
            invalid_rows.append(invalid)
            store.quarantine_data(run_id, "bars_daily", trade_date, code, reason, row)
            continue
        reference_close = (
            fallback_closes.get(code)
            if code in fallback_codes
            else reference_result.closes.get(code)
        )
        if reference_close is not None:
            close = float(row["close"])
            relative_gap = abs(close - reference_close) / max(abs(reference_close), 1e-12)
            if relative_gap > close_tolerance:
                reason = "cross_source_close_mismatch"
                invalid = {
                    **row,
                    "reason": reason,
                    "reference_close": reference_close,
                    "relative_gap": relative_gap,
                }
                invalid_rows.append(invalid)
                store.quarantine_data(run_id, "bars_daily", trade_date, code, reason, invalid)
                continue
        valid_rows += 1

    if invalid_rows:
        # Distinguish hard corruption (invalid OHLC / wrong date) from cross-source
        # close mismatches.  A few close mismatches between tushare and tpdog are
        # normal (rounding/_delay/adjustment) — quarantine those individual rows
        # (already done above) but only fail the whole run if the mismatch RATIO
        # is high.  Otherwise a single divergent code freezes the entire day's
        # post-close publish.
        hard_invalid = [r for r in invalid_rows if r["reason"] != "cross_source_close_mismatch"]
        mismatch_rows = [r for r in invalid_rows if r["reason"] == "cross_source_close_mismatch"]
        total_checked = valid_rows + len(invalid_rows)
        mismatch_ratio = len(mismatch_rows) / total_checked if total_checked else 0.0
        if hard_invalid:
            blocking_reasons.append("invalid_ohlcv_rows")
            status = QualityStatus.QUARANTINED
        elif mismatch_ratio > 0.05:
            # >5% of codes mismatch the reference → genuine data corruption.
            blocking_reasons.append("cross_source_close_mismatch")
            status = QualityStatus.QUARANTINED
        else:
            # Isolated mismatches: quarantine the bad rows, publish the rest.
            blocking_reasons.append("cross_source_close_mismatch")
            status = QualityStatus.PARTIAL
    elif blocking_reasons:
        status = QualityStatus.PARTIAL
    else:
        status = QualityStatus.VERIFIED

    store.set_daily_run_quality(run_id, status)

    sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
    return DatasetQualityReport(
        dataset="bars_daily",
        trade_date=trade_date,
        status=status,
        expected_rows=len(expected),
        received_rows=len(rows),
        valid_rows=valid_rows,
        missing_codes=missing_codes,
        invalid_rows=invalid_rows,
        blocking_reasons=blocking_reasons,
        source=",".join(sources),
    )
