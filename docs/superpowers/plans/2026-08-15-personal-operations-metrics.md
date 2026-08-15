# Personal Operations Metrics Plan

**Goal:** Give operators a personal-product dashboard for commercial, engagement and Data Hub health without introducing enterprise dimensions.

**Architecture:** Metrics are read-only aggregates over authoritative product objects for a bounded UTC period. Every query is scoped to personal `user_id`; no organization/grouping schema is added. The dashboard calls one admin-only summary endpoint.

## Metrics

- Active entitlement distribution by personal plan.
- Paid order count and CNY revenue.
- Active personal Data Hub Credentials.
- Data Hub requests, success rate and charged Data Credits.
- Weekly effective research users, deduplicated across saved queries, watchlist, report snapshots, settled research tasks and successful Data Hub calls.

## Tasks

- [x] Add dedup/date-window route tests.
- [x] Implement admin-only aggregate response.
- [x] Render operations dashboard with server data.
- [x] Verify focused backend/frontend/type checks and update evidence matrix.
