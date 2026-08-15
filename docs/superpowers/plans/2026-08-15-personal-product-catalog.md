# Personal Product Catalog Cutover Plan

**Goal:** Replace the legacy three-tier catalog with the four personal products defined by the SigmX total architecture: Free, Desktop Pro, Data Developer, and Pro Bundle.

**Architecture:** Product codes and entitlement keys are the stable contract. The server owns names, prices, billing periods, Research Credit grants, Data Credit grants, Desktop access, and Data Hub dataset groups. Web and Desktop render the server contract and never infer access from Chinese labels.

## Constraints

- Personal users only. No enterprise, organization, member, service-account, or shared-quota model.
- No compatibility aliases for `advanced`, `pro`, or `enterprise`.
- Existing legacy catalog rows are removed during startup migration; historical immutable order snapshots remain readable as text.
- `Data Developer` works without Desktop; `Desktop Pro` includes only the basic Data Hub allowance; `Pro Bundle` combines full Desktop and expanded Data Hub access.

## Tasks

- [x] Add failing catalog, entitlement, activation, route, and UI contract tests for all four product codes.
- [x] Replace domain enums and server catalog; migrate active legacy grants/codes/catalog rows out.
- [x] Update admin and personal Web surfaces to render four-product terminology.
- [x] Verify Data Hub and Desktop enforcement for each product.
- [ ] Run backend/frontend/build verification and update the total architecture record.
