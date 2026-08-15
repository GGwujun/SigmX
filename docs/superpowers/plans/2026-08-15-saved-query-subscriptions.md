# Saved Query Subscription Plan

**Goal:** Let individuals subscribe to a saved Web query for daily or weekly review reminders in the unified notification inbox.

**Architecture:** A user-owned subscription points to an existing user-owned saved query. Due processing is idempotent per scheduled occurrence, emits a `cloud` notification with the saved query ID (not Desktop/private content), and advances `next_run_at`. Notification reads process due subscriptions for that user so in-app delivery works without a second service.

## Constraints

- Personal ownership is checked on create/list/delete.
- Frequencies are fixed to `daily` and `weekly`.
- One active subscription per saved query.
- Due processing never embeds report files, positions, local context or Credentials.
- Reprocessing the same occurrence does not duplicate a notification.

## Tasks

- [x] Add failing ownership/schedule/idempotency tests.
- [x] Add subscription service and due notification emission.
- [x] Add personal APIs and `/me` controls.
- [x] Verify focused backend/frontend tests and update evidence matrix.
