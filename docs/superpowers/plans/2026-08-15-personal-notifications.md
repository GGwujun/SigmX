# Personal Notification Center Plan

**Goal:** Provide a unified personal notification inbox and preferences for budget and product events, surfaced in `/me` and account settings.

**Architecture:** Notifications are immutable user-owned event snapshots with optional `read_at`. Preferences suppress future delivery, not the underlying audit event. Data Hub thresholds and successful commerce activations emit deterministic notifications in the same business transaction.

## Constraints

- Personal `user_id` ownership only.
- Mark-read is owner checked and idempotent.
- Budget threshold notifications are unique per Credential/UTC date/threshold.
- Disabling a preference never deletes historical notifications or budget audit events.
- Notification bodies contain no Credential secret, request query, response body or private Desktop content.

## Tasks

- [x] Add schema/service tests for ownership, preference and uniqueness.
- [x] Emit budget and commerce notifications transactionally.
- [x] Add inbox/preference APIs and `/me` UI.
- [x] Verify focused backend/frontend/type checks and update evidence matrix.
