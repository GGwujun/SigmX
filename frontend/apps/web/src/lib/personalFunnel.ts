export type PersonalFunnelEvent =
  | "landing_view" | "search_submitted" | "result_view" | "pricing_view"
  | "register_started" | "register_completed" | "login_completed"
  | "download_clicked" | "checkout_intent";

const SESSION_KEY = "sigmx_anonymous_funnel_session";

function sessionId(): string {
  const existing = window.localStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const created = `web_${crypto.randomUUID().replace(/-/g, "")}`;
  window.localStorage.setItem(SESSION_KEY, created);
  return created;
}

/** Best-effort, privacy-minimal product telemetry. Never blocks navigation. */
export function trackPersonalFunnel(eventName: PersonalFunnelEvent): void {
  if (navigator.userAgent.toLowerCase().includes("jsdom")) return;
  const body = JSON.stringify({ anonymous_session_id: sessionId(), event_name: eventName });
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/public/funnel-events", new Blob([body], { type: "application/json" }));
      return;
    }
    void fetch("/api/public/funnel-events", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
  } catch {
    // Analytics must not alter the product journey.
  }
}
