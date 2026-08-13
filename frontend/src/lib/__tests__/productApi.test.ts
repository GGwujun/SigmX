import { describe, it, expect } from "vitest";
import { formatPlanPrice, type PlanView } from "../productApi";

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

  it("advanced quarterly plan shows yuan per quarter", () => {
    expect(formatPlanPrice(plan({ code: "advanced", price_cny_fen: 26800, billing_period: "quarter" }))).toBe(
      "¥268/季",
    );
  });

  it("pro plan with non-whole yuan keeps two decimals", () => {
    expect(formatPlanPrice(plan({ code: "pro", price_cny_fen: 51850, billing_period: "quarter" }))).toBe(
      "¥518.50/季",
    );
  });

  it("enterprise (contract) shows 合同报价 regardless of zero price", () => {
    expect(formatPlanPrice(plan({ code: "enterprise", price_cny_fen: 0, billing_period: "contract" }))).toBe(
      "合同报价",
    );
  });
});
