"""Central publication policy for canonical market datasets.

Row-count policy is intentionally only the first layer. Semantic row
validators live in :mod:`dataset_contracts`; this registry decides whether a
degraded dataset blocks the whole snapshot or is published as unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetContract:
    minimum_rows: int = 1
    blocking: bool = False
    recommendation_input: bool = False
    # When True, a dataset that *fetched* rows but every row failed semantic
    # validation (valid_rows == 0 with received_rows > 0) still blocks
    # publication.  This distinguishes "data is corrupt" from "provider was
    # rate-limited / coverage incomplete" — the former must never ship even for
    # an advisory dataset, the latter degrades gracefully.
    hard_fail_on_zero_valid: bool = False


# Datasets whose absence means the snapshot is structurally unusable.  A
# failed *critical* contract blocks publication of the whole run — the live DB
# keeps the previous verified snapshot rather than shipping a broken one.
# NOTE: daily_basic is intentionally NOT critical — it's tushare-only with no
# fallback source, and tushare rate-limits it to ~1 call/min, so making it
# blocking lets a single rate-limited fetch freeze the whole core publish.
# It degrades to advisory instead (PARTIAL when absent, but core still ships).
_CRITICAL: dict[str, int] = {
    "calendar": 1,
    "master": 3000,
    "index": 4,
}

# Datasets the recommendation pipeline consumes but whose temporary
# unavailability is *degradable*, not fatal.  Realtime quotes at the close,
# board-member lists under TPDog rate limits, and per-sector snapshots can fall
# short of their minimum without making the core master/daily/index universe
# wrong.  A failed *advisory* contract records PARTIAL + a blocking_reason (so
# the recommendation layer can sense the degradation) but still publishes the
# snapshot — the previous behaviour blocked the entire run on any one of these,
# which is why a single rate-limited provider froze the live DB for the day.
_ADVISORY: dict[str, int] = {
    "board_members": 3000,
    "realtime": 3000,
    "daily_basic": 1000,
    "capital_rank": 20,
    "sector_capital": 10,
    "sector_snapshot": 10,
    "sector_snapshot_industry": 10,
    "sector_snapshot_concept": 10,
    "market_breadth": 1,
    "stage_snapshot": 1,
    "ths_hot": 5,
    "zt_pool": 1,
    "hot_list": 20,
    "cls_telegraph": 5,
}

_RECOMMENDATION_INPUTS = {
    "daily",
    "realtime",
    "capital_rank",
    "sector_capital",
    "sector_snapshot",
    "market_breadth",
    "stage_snapshot",
    "ths_hot",
    "zt_pool",
    "hot_list",
    "northbound",
    "cls_telegraph",
    "stock_news",
    "fund_flow_daily",
}

# Advisory datasets whose rows are re-read from the shadow DB and run through
# dataset_contracts.validate_dataset in the worker.  See _semantic_rows in
# market_sync_worker.py — keep this set in sync with it.
_SEMANTICALLY_VALIDATED = {
    "realtime",
    "capital_rank",
    "sector_capital",
    "market_breadth",
    "master",
    "board_members",
}


def contract_for(dataset: str) -> DatasetContract:
    if dataset in _CRITICAL:
        minimum = _CRITICAL[dataset]
        blocking = True
    elif dataset in _ADVISORY:
        minimum = _ADVISORY[dataset]
        blocking = False
    else:
        minimum = 1
        blocking = False
    # Datasets whose rows are re-read and semantically validated must never
    # ship when every fetched row was rejected (corruption), even though they
    # are otherwise advisory.  Coverage shortfall still degrades gracefully.
    hard_fail = dataset in _SEMANTICALLY_VALIDATED
    return DatasetContract(
        minimum_rows=minimum,
        blocking=blocking,
        recommendation_input=dataset in _RECOMMENDATION_INPUTS,
        hard_fail_on_zero_valid=hard_fail,
    )
