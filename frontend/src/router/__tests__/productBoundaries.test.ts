import { describe, expect, it } from "vitest";

import { DESKTOP_ROUTE_PATHS, WEB_ROUTE_PATHS } from "@/router/productRoutes";

const PUBLIC_WEB_ROUTES = [
  "/",
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

describe("product route boundaries", () => {
  it("keeps every Desktop workbench route out of the Web application", () => {
    expect(WEB_ROUTE_PATHS).toEqual(expect.arrayContaining(PUBLIC_WEB_ROUTES));
    for (const path of DESKTOP_WORKBENCH_ROUTES) {
      expect(WEB_ROUTE_PATHS).not.toContain(path);
    }
  });

  it("keeps every public acquisition route out of the Desktop application", () => {
    expect(DESKTOP_ROUTE_PATHS).toEqual(expect.arrayContaining(DESKTOP_WORKBENCH_ROUTES));
    for (const path of PUBLIC_WEB_ROUTES) {
      expect(DESKTOP_ROUTE_PATHS).not.toContain(path);
    }
  });

  it("allows both products to expose the shared personal account routes", () => {
    const shared = ["/me", "/account", "/account/data-hub"];
    expect(WEB_ROUTE_PATHS).toEqual(expect.arrayContaining(shared));
    expect(DESKTOP_ROUTE_PATHS).toEqual(expect.arrayContaining(shared));
  });
});
