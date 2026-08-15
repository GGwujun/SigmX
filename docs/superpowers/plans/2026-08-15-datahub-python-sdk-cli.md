# Data Hub Python SDK and CLI Plan

**Goal:** Ship an installable personal Data Hub Python SDK and CLI over the existing REST contract.

**Architecture:** A small dependency-free package uses `urllib` and reads Credentials only from explicit constructor input or `SIGMX_DATAHUB_KEY`. It exposes generic allowlisted-path GET plus common helpers and returns response metadata including request ID and Data Credit charges.

## Constraints

- Never persist or print the Credential.
- Require `sxd_live_` Credentials.
- Require HTTPS except explicit localhost development URLs.
- Surface structured API errors without echoing authorization headers.
- CLI query parameters are explicit repeatable `--param key=value` arguments.

## Tasks

- [x] Add failing client/security/CLI tests.
- [x] Add package, typed client and response metadata.
- [x] Add CLI and install/documentation examples.
- [x] Verify package tests, wheel build and update architecture evidence.
