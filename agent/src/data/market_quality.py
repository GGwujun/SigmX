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
    if any(str(row.get("source") or "").startswith("tpdog.") for row in rows):
        blocking_reasons.append("unverified_fallback_source")
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
        reference_close = reference_result.closes.get(code)
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
        blocking_reasons.append("cross_source_close_mismatch" if any(
            row["reason"] == "cross_source_close_mismatch" for row in invalid_rows
        ) else "invalid_ohlcv_rows")
        status = QualityStatus.QUARANTINED
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
