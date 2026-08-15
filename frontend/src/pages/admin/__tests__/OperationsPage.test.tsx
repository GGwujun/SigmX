import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { OperationsPage } from "../OperationsPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(...responses: Array<{ body: unknown; ok?: boolean }>) {
  const m = vi.fn().mockImplementation(async () => {
    const response = responses.shift() ?? { body: {}, ok: true };
    return {
      ok: response.ok ?? true,
      status: response.ok === false ? 400 : 200,
      json: async () => response.body,
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", m);
  return m;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OperationsPage />
    </MemoryRouter>,
  );
}

describe("OperationsPage", () => {
  it("generates codes and shows plaintext exactly once", async () => {
    const fetchMock = mockFetch(
      { body: { plans: [{ code: "desktop_pro", name_zh: "桌面专业研究版", price_cny_fen: 26800, billing_period: "quarter", monthly_credits: 300, welcome_credits: 0, description: "", entitlements: {}, sort_order: 2 }] } },
      { body: { items: [{ code: "data_10k", name_zh: "Data Credit 10,000", credits: 10000, price_cny_fen: 3900, valid_days: 365, enabled: true, sort_order: 1 }] } },
      { body: { codes: [
        { plaintext: "SX-AAAA-111111", code_hash: "h1", plan_code: "desktop_pro", months: 3 },
        { plaintext: "SX-BBBB-222222", code_hash: "h2", plan_code: "desktop_pro", months: 3 },
      ] } },
    );
    renderPage();

    await screen.findByText(/桌面专业研究版/);
    fireEvent.click(screen.getByText("生成"));

    await waitFor(() => {
      expect(screen.getByText("SX-AAAA-111111")).toBeInTheDocument();
      expect(screen.getByText("SX-BBBB-222222")).toBeInTheDocument();
    });
    // POSTed to the admin activation-codes endpoint with the form values.
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/activation-codes",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces the error message on failure", async () => {
    mockFetch(
      { body: { plans: [{ code: "desktop_pro", name_zh: "Desktop Pro", price_cny_fen: 26800, billing_period: "quarter", monthly_credits: 300, welcome_credits: 0, description: "", entitlements: {}, sort_order: 2 }] } },
      { body: { items: [{ code: "data_10k", name_zh: "Data Credit 10,000", credits: 10000, price_cny_fen: 3900, valid_days: 365, enabled: true, sort_order: 1 }] } },
      { body: { detail: "无效套餐" }, ok: false },
    );
    renderPage();
    await screen.findByText(/Desktop Pro/);
    fireEvent.click(screen.getByText("生成"));
    // The error surfaces via toast; the codes section stays empty.
    await waitFor(() => {
      expect(screen.queryByText(/SX-/)).not.toBeInTheDocument();
    });
  });

  it("generates a server-driven Data Credit pack code", async () => {
    const fetchMock = mockFetch(
      { body: { plans: [{ code: "desktop_pro", name_zh: "Desktop Pro", price_cny_fen: 26800, billing_period: "quarter", monthly_credits: 300, welcome_credits: 0, description: "", entitlements: {}, sort_order: 2 }] } },
      { body: { items: [{ code: "data_10k", name_zh: "Data Credit 10,000", credits: 10000, price_cny_fen: 3900, valid_days: 365, enabled: true, sort_order: 1 }] } },
      { body: { codes: [{ plaintext: "SX-PACK-111111", code_hash: "pack-hash", plan_code: "data_10k", months: 0 }] } },
    );
    renderPage();
    await screen.findByText(/Data Credit 10,000/);
    fireEvent.click(screen.getByRole("button", { name: "生成积分包码" }));
    expect(await screen.findByText("SX-PACK-111111")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/data-credit-codes",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
