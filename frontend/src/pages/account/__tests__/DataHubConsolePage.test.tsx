import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, vi } from "vitest";

import { DataHubConsolePage } from "../DataHubConsolePage";


function installFetch() {
  const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
    if (url === "/api/data-credits/me") return Promise.resolve(ok({ available: 1000, expiring_soon: 100 }));
    if (url === "/api/data-credits/lots") return Promise.resolve(ok({ lots: [{ id: "l1", amount_total: 1000, amount_remaining: 997, source: "monthly", expires_at: "2026-08-31T23:59:59Z", created_at: "2026-08-01T00:00:00Z" }] }));
    if (url === "/api/data-credits/ledger") return Promise.resolve(ok({ entries: [{ id: "e1", operation: "settle", delta: -3, lot_id: "l1", reservation_id: "r1", created_at: "2026-08-15T00:00:00Z" }] }));
    if (url === "/api/catalog/data-credit-packs") return Promise.resolve(ok({ items: [{ code: "data_10k", name_zh: "Data Credit 10,000", credits: 10000, price_cny_fen: 3900, valid_days: 365, enabled: true, sort_order: 1 }] }));
    if (url === "/api/data-credits/redeem" && options?.method === "POST") return Promise.resolve(ok({ order_id: "o-pack", plan_code: "data_10k", months: 0, credits_granted: 10000, replayed: false }));
    if (url === "/api/datahub/catalog") return Promise.resolve(ok({ items: [{ endpoint_code: "health", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/health", dataset_group: "basic.v1", pricing_mode: "free", base_cost: 0, unit_name: null, unit_size: null, unit_cost: null, max_cost: null, enabled: true }] }));
    if (url === "/api/datahub/usage") return Promise.resolve(ok({ total_requests: 2, successful_requests: 2, credits_charged: 3, by_endpoint: [] }));
    if (url === "/api/datahub/credentials" && options?.method === "POST") {
      return Promise.resolve(ok({ id: "k1", plaintext: "sxd_live_secret", key_prefix: "sxd_live_sec", name: "研究脚本", scopes: ["health"], ip_allowlist: [], expires_at: null, last_used_at: null, created_at: "2026-08-15T00:00:00Z", revoked_at: null }));
    }
    if (url === "/api/datahub/credentials/k1/budget" && options?.method === "PUT") return Promise.resolve(ok({ credential_id: "k1", daily_limit: 100, spent_today: 20, remaining_today: 80, utc_date: "2026-08-15" }));
    if (url === "/api/datahub/credentials") return Promise.resolve(ok({ items: [{ id: "k1", key_prefix: "sxd_live_sec", name: "研究脚本", scopes: ["health"], ip_allowlist: [], expires_at: null, last_used_at: null, created_at: "2026-08-15T00:00:00Z", revoked_at: null }] }));
    if (url === "/api/datahub/logs?limit=50&errors_only=false") return Promise.resolve(ok({ items: [{ request_id: "r-bad", credential_id: "k1", credential_name: "研究脚本", key_prefix: "sxd_live_sec", endpoint_code: "health", status_code: 500, requested_units: 1, actual_units: 0, credits_authorized: 0, credits_charged: 0, duration_ms: 8, error_code: "handler_error", created_at: "2026-08-15T00:00:00Z" }], next_cursor: null }));
    if (url === "/api/datahub/budget-alerts?limit=100") return Promise.resolve(ok({ items: [{ credential_id: "k1", credential_name: "研究脚本", utc_date: "2026-08-15", threshold_percent: 80, spent: 80, daily_limit: 100, created_at: "2026-08-15T00:00:00Z" }] }));
    if (url === "/api/datahub/budgets") return Promise.resolve(ok({ items: [] }));
    if (url === "/api/v1/health") return Promise.resolve({ ok: true, status: 200, headers: new Headers({ "X-DataHub-Credits-Charged": "0", "X-Request-ID": "req1" }), text: async () => '{"ok":true}', json: async () => ({ ok: true }) } as Response);
    return Promise.resolve(ok({ ok: true }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

afterEach(() => vi.restoreAllMocks());

describe("DataHubConsolePage", () => {
  it("shows Data Credit balance and metered usage", async () => {
    installFetch();
    render(<MemoryRouter><DataHubConsolePage /></MemoryRouter>);
    expect(await screen.findByText("1,000")).toBeInTheDocument();
    expect(screen.getByText(/本期已扣 3 Data Credit/)).toBeInTheDocument();
    expect(screen.getByText("积分批次与账本")).toBeInTheDocument();
    expect(screen.getByText(/剩余 997 \/ 1,000/)).toBeInTheDocument();
    expect(screen.getByText("-3")).toBeInTheDocument();
  });

  it("creates a key and clears the one-time secret when closed", async () => {
    const fetchMock = installFetch();
    render(<MemoryRouter><DataHubConsolePage /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("Key 名称"), { target: { value: "研究脚本" } });
    fireEvent.change(screen.getByLabelText("Scope"), { target: { value: "health" } });
    fireEvent.change(screen.getByLabelText("到期时间"), { target: { value: "2026-12-31T18:30" } });
    fireEvent.click(screen.getByRole("button", { name: "创建 Key" }));
    expect(await screen.findByText("sxd_live_secret")).toBeInTheDocument();
    expect(screen.getByText(/仅显示一次/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "我已保存" }));
    await waitFor(() => expect(screen.queryByText("sxd_live_secret")).not.toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([url, options]) => url === "/api/datahub/credentials" && options?.method === "POST");
    expect(JSON.parse(call?.[1]?.body as string)).toMatchObject({ name: "研究脚本", scopes: ["health"], expires_at: new Date("2026-12-31T18:30").toISOString() });
  });

  it("shows logs and budget alerts, saves a daily credit budget, and links to API docs for debugging", async () => {
    const fetchMock = installFetch();
    render(<MemoryRouter><DataHubConsolePage /></MemoryRouter>);
    expect(await screen.findByText("handler_error")).toBeInTheDocument();
    expect(screen.getByText(/80%/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("研究脚本每日预算"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "保存研究脚本预算" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/datahub/credentials/k1/budget", expect.objectContaining({ method: "PUT", body: JSON.stringify({ daily_limit: 100 }) })));
    expect(screen.queryByRole("heading", { name: "在线调试" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "接口目录" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "接口文档与在线调试" })).toHaveAttribute("href", "/docs/data-hub/");
  });

  it("shows server-driven Data Credit packs and redeems a prepaid pack code", async () => {
    const fetchMock = installFetch();
    render(<MemoryRouter><DataHubConsolePage /></MemoryRouter>);
    expect(await screen.findByText("Data Credit 10,000")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Data Credit 积分包激活码"), { target: { value: "SX-PACK-ABC123" } });
    fireEvent.click(screen.getByRole("button", { name: "兑换积分包" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/data-credits/redeem",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "SX-PACK-ABC123", idempotency_key: "data-pack:SX-PACK-ABC123" }) }),
    ));
  });
});
