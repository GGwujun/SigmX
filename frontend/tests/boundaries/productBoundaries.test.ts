import { describe, expect, it } from "vitest";

// Frozen product contract, expressed as literals: a root-level test must not
// import code from either app (each app owns an independent copy of its
// route constants). The per-app route-tree assertions live next to each
// router in apps/*/src/router/__tests__/.
const PUBLIC_WEB_ROUTES = [
  "/",
  "/intelligence",
  "/skills",
  "/skills/:slug",
  "/pricing",
  "/product/data-hub",
  "/product/desktop",
  "/download",
  "/query/:id",
  "/stock/:code",
  "/fund/:code",
  "/research/:slug",
];

const DESKTOP_WORKBENCH_ROUTES = [
  "/app",
  "/research",
  "/market",
  "/quant",
  "/tracking",
  "/runs",
  "/assets",
  "/cloud",
  "/settings",
];

// Account routes are intentionally present in both products (each app
// registers its own copy since the de-share refactor).
const SHARED_ACCOUNT_ROUTES = ["/me", "/account", "/account/data-hub"];

describe("product route boundaries", () => {
  it("keeps the public route list free of Desktop workbench routes", () => {
    for (const path of DESKTOP_WORKBENCH_ROUTES) {
      expect(PUBLIC_WEB_ROUTES).not.toContain(path);
    }
  });

  it("keeps the workbench route list free of public acquisition routes", () => {
    for (const path of PUBLIC_WEB_ROUTES) {
      expect(DESKTOP_WORKBENCH_ROUTES).not.toContain(path);
    }
  });

  it("documents the account routes both products own copies of", () => {
    for (const path of SHARED_ACCOUNT_ROUTES) {
      expect(PUBLIC_WEB_ROUTES).not.toContain(path);
      expect(DESKTOP_WORKBENCH_ROUTES).not.toContain(path);
    }
  });
});
