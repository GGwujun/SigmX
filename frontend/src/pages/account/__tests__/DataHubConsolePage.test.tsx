import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, vi } from "vitest";

import { DataHubConsolePage } from "../DataHubConsolePage";


function installFetch() {
  const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
    if (url === "/api/data-credits/me") return Promise.resolve(ok({ available: 1000, expiring_soon: 100 }));
    if (url === "/api/data-credits/lots") return Promise.resolve(ok({ lots: [] }));
    if (url === "/api/data-credits/ledger") return Promise.resolve(ok({ entries: [] }));
    if (url === "/api/datahub/catalog") return Promise.resolve(ok({ items: [{ endpoint_code: "health", dataset_group: "basic.v1", pricing_mode: "free", base_cost: 0 }] }));
    if (url === "/api/datahub/usage") return Promise.resolve(ok({ total_requests: 2, successful_requests: 2, credits_charged: 3, by_endpoint: [] }));
    if (url === "/api/datahub/credentials" && options?.method === "POST") {
      return Promise.resolve(ok({ id: "k1", plaintext: "sxd_live_secret", key_prefix: "sxd_live_sec", name: "研究脚本", scopes: ["health"], ip_allowlist: [], expires_at: null, last_used_at: null, created_at: "2026-08-15T00:00:00Z", revoked_at: null }));
    }
    if (url === "/api/datahub/credentials") return Promise.resolve(ok({ items: [] }));
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
  });

  it("creates a key and clears the one-time secret when closed", async () => {
    const fetchMock = installFetch();
    render(<MemoryRouter><DataHubConsolePage /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("Key 名称"), { target: { value: "研究脚本" } });
    fireEvent.change(screen.getByLabelText("Scope"), { target: { value: "health" } });
    fireEvent.click(screen.getByRole("button", { name: "创建 Key" }));
    expect(await screen.findByText("sxd_live_secret")).toBeInTheDocument();
    expect(screen.getByText(/仅显示一次/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "我已保存" }));
    await waitFor(() => expect(screen.queryByText("sxd_live_secret")).not.toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([url, options]) => url === "/api/datahub/credentials" && options?.method === "POST");
    expect(JSON.parse(call?.[1]?.body as string)).toMatchObject({ name: "研究脚本", scopes: ["health"] });
  });
});
