# Public SEO Rendering Plan

**Goal:** Return route-specific, indexable HTML for the public Web funnel while keeping the authenticated Portal and Desktop workbench as SPA routes.

**Architecture:** FastAPI intercepts browser HTML GETs for the explicit public-route allowlist, reads the built Vite shell, and injects escaped semantic fallback content, title, description, canonical/OG metadata and JSON-LD. React replaces the fallback content on boot. API/JSON requests and all private routes remain unchanged.

## Constraints

- Only public funnel routes are rendered.
- Every path-derived value is escaped before entering HTML or JSON-LD.
- No account, token, local Desktop or private report content enters the document.
- Dynamic stock/fund/query paths receive useful route-specific text even before JavaScript.
- HTML is `no-store`; fingerprinted assets retain immutable caching.

## Tasks

- [x] Add failing allowlist, escaping and metadata tests.
- [x] Implement semantic public HTML renderer.
- [x] Integrate with FastAPI browser HTML middleware.
- [x] Build frontend and verify rendered artifacts.
