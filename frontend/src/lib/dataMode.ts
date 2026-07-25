/**
 * Data Hub connected-mode configuration.
 *
 * Two modes:
 *   "standalone" — local market.db, local worker pulls data (default, free)
 *   "connected"  — remote Data Hub, /api/v1/* fetched from server (subscription)
 *
 * Persisted to localStorage. Used by api.ts to route data requests.
 */

const MODE_KEY = "sigmx_data_mode";
const HUB_URL_KEY = "sigmx_data_hub_url";
const HUB_KEY_KEY = "sigmx_data_hub_key";

export type DataMode = "standalone" | "connected";

export function getDataMode(): DataMode {
  try {
    const v = window.localStorage.getItem(MODE_KEY);
    if (v === "connected") return "connected";
  } catch { /* ignore */ }
  return "standalone";
}

export function setDataMode(mode: DataMode): void {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch { /* ignore */ }
}

export function getDataHubUrl(): string {
  try {
    return window.localStorage.getItem(HUB_URL_KEY) || "";
  } catch { return ""; }
}

export function setDataHubUrl(url: string): void {
  try {
    const trimmed = url.trim().replace(/\/+$/, ""); // strip trailing slashes
    if (trimmed) window.localStorage.setItem(HUB_URL_KEY, trimmed);
    else window.localStorage.removeItem(HUB_URL_KEY);
  } catch { /* ignore */ }
}

export function getDataHubKey(): string {
  try {
    return window.localStorage.getItem(HUB_KEY_KEY) || "";
  } catch { return ""; }
}

export function setDataHubKey(key: string): void {
  try {
    const trimmed = key.trim();
    if (trimmed) window.localStorage.setItem(HUB_KEY_KEY, trimmed);
    else window.localStorage.removeItem(HUB_KEY_KEY);
  } catch { /* ignore */ }
}

/** True if connected mode is active AND a hub URL is configured. */
export function isDataHubConnected(): boolean {
  return getDataMode() === "connected" && !!getDataHubUrl() && !!getDataHubKey();
}

/** Resolve a /api/v1/* URL — routes to Data Hub when connected, localhost otherwise. */
export function resolveApiUrl(path: string): string {
  if (getDataMode() === "connected") {
    const hub = getDataHubUrl();
    if (hub) return `${hub}${path}`;
  }
  return path; // relative to same origin
}

/** Headers to add when calling Data Hub endpoints. */
export function dataHubHeaders(): Record<string, string> {
  if (getDataMode() === "connected") {
    const key = getDataHubKey();
    if (key) return { "X-API-Key": key };
  }
  return {};
}
