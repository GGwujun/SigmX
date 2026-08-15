# SigmX Total Architecture Evidence Matrix

This is the completion gate for `2026-08-15-sigmx-product-architecture-design.md`. A row is complete only when code and an executable verification both exist.

| Architecture requirement | Current evidence | Status / remaining work |
|---|---|---|
| Three independent products and route shells | Public routes, `/me` account shell, Desktop `/app`, Data Hub catalog/gateway; router boundary tests | Complete |
| Public acquisition funnel | Search, query, stock/fund, research snapshot, product, pricing, download and docs routes; public research tests; route-specific semantic HTML | Complete |
| Logged-in cloud assets | Saved queries, watchlist, report snapshots, task handoffs and `/me` | Complete |
| Desktop Financial Harness | Runtime context, tool contracts, governance states, run records, Connected sessions and UI status | Complete for the specified non-trading scope |
| Secure cross-terminal research loop | Hashed one-time handoff, strict `sigmx://research/` parser, device-bound consumption, explicit redacted report publication | Complete |
| Independent Data Hub | Versioned endpoint catalog, personal Credentials, scopes/IP/rotation/revoke, gateway limits and Data Credit settlement | Complete |
| Developer console | Catalog/docs, Credential management, debugger, lots/ledger, logs/errors, UTC budgets and 50/80/100 alerts | Complete |
| Four personal products | `free`, `desktop_pro`, `data_developer`, `pro_bundle`; old personal/enterprise codes removed; server-driven names/prices | Complete |
| Double-credit separation | Independent stores, lots, ledgers, authorization/reservation and settlement paths | Complete |
| Personal renewal | Same-plan activation extends from current expiry | Complete |
| Personal bills and consumption insight | `/api/billing/summary`, paid order amount, 30-day Research/Data Credit consumption, account display | Complete |
| Real checkout/payment/refund | Provider protocol exists; only activation-code provider is operational | Missing: signed Alipay/WeChat provider and production credentials; explicitly excluded from first-phase §15 but required by rollout §13.7 |
| Purchased Data Credit packs | Server-driven 10k/50k/200k pack catalog; hashed prepaid codes; atomic order, `purchase` lot, 365-day expiry, audit; personal/admin UI | Complete for the operational activation-code payment channel |
| Personal notifications/subscriptions | User-owned inbox/preferences; transactional budget and commerce events; owner-scoped mark-read; personal daily/weekly saved-query review subscriptions and idempotent due notifications; `/me` UI | Complete for personal saved-query review; published report delivery is intentionally not duplicated because reports are immutable snapshots |
| Operations console | Plan/pack activation-code generation, immutable commerce audit, personal product metrics | Partial: catalog editing, external-payment refund, credit adjustment, device/credential operations and content controls remain missing |
| Metrics and funnel | Admin summary for plan distribution, paid orders/revenue, active Credentials, Data Hub success/cost, deduplicated weekly effective research users, and the anonymous personal-user acquisition stages | Complete; funnel accepts only fixed events, deduplicates per browser/stage/day and stores no PII, query, instrument, IP, user-agent or arbitrary metadata |
| SSR/static public delivery | FastAPI public-route allowlist injects escaped semantic HTML, canonical/OG metadata and JSON-LD into built Vite shell; private routes excluded; artifact verified | Complete |
| SDK and CLI delivery | Dependency-free `sigmx-datahub` wheel, typed response metadata, secure client, `sigmx-data` CLI and public docs | Complete |
| Full verification | Product/Harness/Data Hub suites and frontend/build pass | Repository-wide backend suite has unrelated Windows/environment and legacy failures; completion requires scoped gates plus documented baseline |

## Next implementation order

1. Expand safe personal operations controls where domain services already support auditable mutations.
2. Integrate a real payment provider only with real merchant configuration and signed webhook verification.
3. Run the scoped completion gates and record the repository-wide baseline separately.
