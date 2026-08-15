# Personal Data Credit Pack Implementation Plan

**Goal:** Let an individual buy/redeem additional Data Credits independently of a plan, with a server-driven pack catalog, idempotent order/audit trail, and 12-month expiry.

**Architecture:** Credit packs are products, not entitlements. The server catalog exposes stable pack code, amount, price and validity. The currently operational activation-code payment channel can issue a prepaid pack code; redeeming it atomically creates a paid order, grants a `purchase` Data Credit lot, consumes the hashed code once and writes immutable audit. No endpoint may pretend an external Alipay/WeChat payment succeeded.

## Constraints

- Personal `user_id` ownership only.
- Pack codes and prices are server-driven.
- Plaintext code is displayed only once and only its SHA-256 hash is stored.
- Redeem is idempotent and a code is globally single-use.
- Purchased lots expire 365 days after redemption and are consumed by earliest expiry.
- Research Credits and Data Credits remain separate.

## Tasks

- [x] Add catalog/schema and failing service tests.
- [x] Add atomic prepaid pack redemption and personal order serialization.
- [x] Add admin generation and personal account UI.
- [x] Verify idempotency, ownership, expiry, ledger and TypeScript checks.
