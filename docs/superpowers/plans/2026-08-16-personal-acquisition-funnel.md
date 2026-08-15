# Personal Acquisition Funnel Plan

**Goal:** Measure the anonymous-to-personal-user Web funnel without collecting PII or adding enterprise lead concepts.

## Constraints

- Only allow a fixed vocabulary of product events.
- Use a random browser session ID; never accept email, phone, query text, instrument code, IP, user agent, or arbitrary metadata.
- Aggregate unique sessions by stage for operations; do not expose raw visitor trails in the admin UI.
- Product analytics failure must never block the user journey.

## Tasks

- [x] Add privacy, validation, daily deduplication, and aggregation tests.
- [x] Add event storage and public ingestion API.
- [x] Instrument public personal-user journey stages.
- [x] Add aggregate funnel to personal operations metrics and verify.
