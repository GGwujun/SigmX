import { describe, it, expect } from "vitest";
import { formatPlanPrice, getOperationsState, updateOperationalEndpoint, type PlanView } from "../productApi";

function plan(over: Partial<PlanView>): PlanView {
  return {
    code: "free",
    name_zh: "免费版",
    price_cny_fen: 0,
    billing_period: "one_time",
    monthly_credits: 0,
    welcome_credits: 0,
    description: "",
    entitlements: {},
    sort_order: 1,
    ...over,
  };
}

describe("formatPlanPrice", () => {
  it("free plan shows 免费", () => {
    expect(formatPlanPrice(plan({ code: "free", price_cny_fen: 0 }))).toBe("免费");
  });

  it("desktop pro quarterly plan shows yuan per quarter", () => {
    expect(formatPlanPrice(plan({ code: "desktop_pro", price_cny_fen: 26800, billing_period: "quarter" }))).toBe(
      "¥268/季",
    );
  });

  it("bundle plan with non-whole yuan keeps two decimals", () => {
    expect(formatPlanPrice(plan({ code: "pro_bundle", price_cny_fen: 51850, billing_period: "quarter" }))).toBe(
      "¥518.50/季",
    );
  });

  it("enterprise (contract) shows 合同报价 regardless of zero price", () => {
    expect(formatPlanPrice(plan({ code: "enterprise", price_cny_fen: 0, billing_period: "contract" }))).toBe(
      "合同报价",
    );
  });
});

describe("operations API", () => {
  it("loads state and updates endpoint policy with an audited reason", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ products: [], endpoints: [], content: [], refunds: [], metrics: {}, audit: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    await getOperationsState();
    await updateOperationalEndpoint("market.daily", { enabled: true, credit_cost: 3, unit_cost_cny_fen: 1.2, quality_score: 0.998, reason: "接口成本校准" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/operations?days=30");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/admin/operations/endpoints/market.daily");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "PUT" }));
  });
});
