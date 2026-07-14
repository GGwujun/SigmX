"""Strict quality contracts shared by market-data writers and readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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
