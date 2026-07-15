"""Semantic contracts and observable provider fallback for market datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    rows: list[dict[str, Any]]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProviderAttempt:
    source: str
    valid: bool
    row_count: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProviderResult:
    dataset: str
    source: str | None
    rows: list[dict[str, Any]]
    attempts: tuple[ProviderAttempt, ...]

    @property
    def valid(self) -> bool:
        return self.source is not None


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        nested = value.get("rows")
        value = nested if isinstance(nested, list) else [value]
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value)[:10])
        return True
    except (TypeError, ValueError):
        return False


def validate_dataset(name: str, value: Any, *, trade_date: str | None = None) -> ValidationResult:
    rows = _rows(value)
    reasons: list[str] = []
    if not rows:
        return ValidationResult(False, [], ("no usable rows",))

    if name == "eps_forecast":
        valid_rows = []
        for row in rows:
            count = row.get("institution_count", row.get("count", 0))
            try:
                usable = int(count or 0) > 0
            except (TypeError, ValueError):
                usable = False
            if usable:
                valid_rows.append(row)
        rows = valid_rows
        if not rows:
            reasons.append("institution_count must be positive")
    elif name == "northbound_flow":
        rows = [row for row in rows if row.get("hgt_yi") is not None or row.get("sgt_yi") is not None]
        if not rows:
            reasons.append("no reliable northbound channel")
    elif name in {"fund_flow_daily", "daily_bars"}:
        date_key = "date" if name == "fund_flow_daily" else "trade_date"
        rows = [row for row in rows if _valid_iso_date(row.get(date_key))]
        if trade_date and rows and max(str(row[date_key])[:10] for row in rows) < trade_date:
            rows = []
            reasons.append("latest row is older than requested trade date")

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        fields = [key for key in ("code", "date", "trade_date", "time", "year") if key in row]
        identity = tuple((key, str(row.get(key))) for key in fields)
        if identity and identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    if not deduped and not reasons:
        reasons.append("no usable rows")
    return ValidationResult(bool(deduped) and not reasons, deduped, tuple(reasons))


def run_provider_chain(
    name: str,
    providers: Sequence[tuple[str, Callable[[], Any]]],
    *,
    trade_date: str | None = None,
) -> ProviderResult:
    attempts: list[ProviderAttempt] = []
    for source, provider in providers:
        try:
            result = validate_dataset(name, provider(), trade_date=trade_date)
        except Exception as exc:
            attempts.append(ProviderAttempt(source, False, 0, (f"provider error: {exc}",)))
            continue
        attempts.append(ProviderAttempt(source, result.valid, len(result.rows), result.reasons))
        if result.valid:
            return ProviderResult(name, source, result.rows, tuple(attempts))
    return ProviderResult(name, None, [], tuple(attempts))
