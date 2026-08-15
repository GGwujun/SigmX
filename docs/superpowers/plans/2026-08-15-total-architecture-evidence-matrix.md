# SigmX Total Architecture Evidence Matrix

This is the completion gate for `2026-08-15-sigmx-product-architecture-design.md`. A row is complete only when code and an executable verification both exist.

| Architecture requirement | Current evidence | Status / remaining work |
|---|---|---|
| Three independent products and route shells | Public routes, `/me` account shell, Desktop `/app`, Data Hub catalog/gateway; router boundary tests | Complete |
| Public acquisition funnel | Search, query, stock/fund, research snapshot, product, pricing, download and docs routes; public research tests | Complete for SPA; SSR/static rendering remains required by §9 |
| Logged-in cloud assets | Saved queries, watchlist, report snapshots, task handoffs and `/me` | Complete |
| Desktop Financial Harness | Runtime context, tool contracts, governance states, run records, Connected sessions and UI status | Complete for the specified non-trading scope |
| Secure cross-terminal research loop | Hashed one-time handoff, strict `sigmx://research/` parser, device-bound consumption, explicit redacted report publication | Complete |
| Independent Data Hub | Versioned endpoint catalog, personal Credentials, scopes/IP/rotation/revoke, gateway limits and Data Credit settlement | Complete |
| Developer console | Catalog/docs, Credential management, debugger, lots/ledger, logs/errors, UTC budgets and 50/80/100 alerts | Complete |
| Four personal products | `free`, `desktop_pro`, `data_developer`, `pro_bundle`; old personal/enterprise codes removed; server-driven names/prices | Complete |
| Double-credit separation | Independent stores, lots, ledgers, authorization/reservation and settlement paths | Complete |
| Personal renewal | Same-plan activation extends from current expiry | Complete |
| Personal bills and consumption insight | `/api/billing/summary`, paid order amount, 30-day Research/Data Credit consumption, account display | In progress in current change |
| Real checkout/payment/refund | Provider protocol exists; only activation-code provider is operational | Missing: signed Alipay/WeChat provider and production credentials; explicitly excluded from first-phase §15 but required by rollout §13.7 |
| Purchased Data Credit packs | Server-driven 10k/50k/200k pack catalog; hashed prepaid codes; atomic order, `purchase` lot, 365-day expiry, audit; personal/admin UI | Complete for the operational activation-code payment channel |
| Personal notifications/subscriptions | User-owned inbox/preferences; transactional budget and commerce events; owner-scoped mark-read; `/me` UI | Notification center complete; saved-query/report delivery subscriptions remain missing |
| Operations console | Activation-code generation and immutable activation audit | Partial: product/price editing, refund workflow, credit adjustment, device/credential operations, content and funnel views missing |
| Metrics and funnel | Domain events and usage records exist in parts | Missing consolidated weekly-effective-research and conversion funnel reporting |
| SSR/static public delivery | React public SPA exists | Missing production SSR/static generation and SEO artifact verification |
| SDK and CLI delivery | REST docs/examples exist | Missing packaged personal Data Hub Python SDK and CLI |
| Full verification | Product/Harness/Data Hub suites and frontend/build pass | Repository-wide backend suite has unrelated Windows/environment and legacy failures; completion requires scoped gates plus documented baseline |

## Next implementation order

1. Finish personal billing summary and account bill view.
2. Add saved-query/report subscriptions and cloud-task completion events.
3. Expand operations and funnel metrics.
4. Add public static/SSR output and Data Hub SDK/CLI packaging.
5. Integrate a real payment provider only with real merchant configuration and signed webhook verification.
