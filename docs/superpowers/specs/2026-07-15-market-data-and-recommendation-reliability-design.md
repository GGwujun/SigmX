# Market Data and Recommendation Reliability Design

## Scope

This change makes the local acquisition, snapshot delivery, and daily recommendation paths deployable and testable. It deliberately does not deploy to production or treat the currently deployed database as an acceptance signal.

## Data-source contracts

Every recommendation-relevant external dataset must pass a semantic contract before it can be stored or mark a sync run as published. Contracts validate required fields, trading date, value ranges, uniqueness, usable-row count, and source identity. Empty-but-truthy provider responses and placeholder rows are failures. A provider chain may fall back only to a source with equivalent field semantics; degraded fields remain absent instead of being fabricated.

The first production contracts cover realtime quotes, daily bars, trade calendar, fund flow, EPS forecast, announcements/news, northbound flow, hot reasons, limit-up pools, and popularity lists. Provider diagnostics record attempts, selected source, rejection reason, and row count.

## Snapshot synchronization

`market-sync` remains the sole writer on the dedicated sync host. `data-sync` exports a consistent SQLite snapshot only from a published run. Delivery is event-driven: it notices a new published `run_id`, sends it immediately, and uses `snapshot_id` for idempotency. Time slots are a safety deadline, not the trigger.

The receiver verifies authentication, manifest consistency, chunk completeness, checksum, gzip integrity, SQLite integrity, and the embedded published run before atomically replacing the query database. Recommendation readiness is represented by a manifest in the database, so business code can reject stale or incomplete input without making external requests.

## Daily recommendation

Recommendation remains isolated to its existing API module, but its evidence becomes local and auditable. The candidate pool requires fresh realtime/daily data and consumes only validated local features. Industry peers come from persisted board membership; no recommendation-time market API call or unrelated hard-coded peer basket is allowed.

The invalid global prediction-event catalyst is disabled unless an event has an explicit symbol or sector mapping. Attribution guardrails run in the real production path before final deterministic scoring. Missing evidence is not treated as a neutral vote: weights are renormalized over available validated features, and candidates below minimum evidence coverage are rejected.

AI remains a bounded explanation/review layer. AI failure must not erase otherwise valid deterministic candidates, and AI cannot lift a candidate through the deterministic eligibility threshold.

## Evidence and promotion

The revised model is a challenger until it has enough forward samples. Reports separate model versions and slots, expose sample size, win rate, mean/median return, drawdown, and coverage, and refuse an “accurate” label below the configured minimum. A promotion gate requires minimum sample size and positive out-of-sample expectancy; otherwise the system reports insufficient evidence.

## Acceptance criteria

- Provider adapters reject semantically invalid successful responses and record fallback diagnostics.
- A published snapshot is delivered once without waiting for a clock minute and cannot replace production if validation fails.
- Recommendation performs no external market-data calls and applies guardrails in its actual execution path.
- Invalid unmapped global events cannot create stock candidates.
- Tests cover failed contracts, fallback selection, event-driven delivery, local peer selection, guardrail wiring, AI degradation, and promotion evidence.
- Existing data, sync, and recommendation test suites pass.
