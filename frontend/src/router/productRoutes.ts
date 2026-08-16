export const SHARED_ACCOUNT_ROUTE_PATHS = [
  "/me",
  "/account",
  "/account/subscription",
  "/account/credits",
  "/account/devices",
  "/account/orders",
  "/account/data-hub",
  "/account/devices/authorize",
] as const;

export const WEB_ROUTE_PATHS = [
  "/",
  "/pricing",
  "/product/data-hub",
  "/product/desktop",
  "/download",
  "/reports/sample/:slug",
  "/query/:id",
  "/stock/:code",
  "/fund/:code",
  "/research/:slug",
  "/docs/data-hub/*",
  "/login",
  "/register",
  "/portal",
  ...SHARED_ACCOUNT_ROUTE_PATHS,
] as const;

export const DESKTOP_ROUTE_PATHS = [
  "/app",
  "/research",
  "/market",
  "/quant",
  "/tracking",
  "/runs",
  "/assets",
  "/cloud",
  "/settings",
  ...SHARED_ACCOUNT_ROUTE_PATHS,
] as const;
