import { describe, expect, it } from "vitest";
import type { RouteObject } from "react-router-dom";

import {
  DESKTOP_ROUTE_PATHS,
  SHARED_ACCOUNT_ROUTE_PATHS,
  WEB_ROUTE_PATHS,
} from "@sigmx/shared/router/productRoutes";
import { desktopRoutes } from "@/router/desktopRouter";

// Routes that are intentionally allowed in both products: the shared account
// area, /login (both routers register it), and "/" (each product needs a root,
// the desktop one is a redirect into the workbench).
const BOTH_PRODUCTS = new Set<string>([...SHARED_ACCOUNT_ROUTE_PATHS, "/login", "/"]);

function joinPath(parent: string, child: string): string {
  if (!parent) return child;
  return `${parent === "/" ? "" : parent}/${child}`;
}

function collectPaths(routes: RouteObject[], parent = ""): string[] {
  const paths: string[] = [];
  for (const route of routes) {
    const nextParent = route.path
      ? route.path.startsWith("/")
        ? route.path
        : joinPath(parent, route.path)
      : parent;
    if (route.path !== undefined) paths.push(nextParent);
    if (route.children) paths.push(...collectPaths(route.children, nextParent));
  }
  return paths;
}

describe("desktop route tree", () => {
  const desktopPaths = collectPaths(desktopRoutes);

  it("registers every DESKTOP_ROUTE_PATHS constant", () => {
    for (const path of DESKTOP_ROUTE_PATHS) {
      expect(desktopPaths).toContain(path);
    }
  });

  it("keeps acquisition-only routes out of the desktop route tree", () => {
    for (const path of WEB_ROUTE_PATHS) {
      if (BOTH_PRODUCTS.has(path)) continue;
      expect(desktopPaths).not.toContain(path);
    }
  });

  it("exposes every shared account route", () => {
    for (const path of SHARED_ACCOUNT_ROUTE_PATHS) {
      expect(desktopPaths).toContain(path);
    }
  });
});
