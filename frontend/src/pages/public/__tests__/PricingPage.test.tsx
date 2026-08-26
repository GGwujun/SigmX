import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PricingPage } from "../PricingPage";
import * as productApi from "@/lib/productApi";

vi.mock("@/lib/productApi", async () => {
  const actual = await vi.importActual<typeof import("@/lib/productApi")>("@/lib/productApi");
  return { ...actual, getPlans: vi.fn() };
});
vi.mock("@/lib/personalFunnel", () => ({ trackPersonalFunnel: vi.fn() }));

const base = { billing_period: "quarter", welcome_credits: 0, description: "套餐", entitlements: { "datahub.enabled": true, "desktop.connected_mode": true, "cloud_ai.enabled": true, "reports.cloud_history": true, "datahub.rate_limit_per_minute": 100, "datahub.concurrent_limit": 2, "datahub.max_rows_per_request": 10000, "datahub.commercial_use": false } };

describe("PricingPage", () => {
  beforeEach(() => {
    vi.mocked(productApi.getPlans).mockResolvedValue([
      { ...base, code: "free", name_zh: "免费版", price_cny_fen: 0, monthly_credits: 0, sort_order: 1, entitlements: { ...base.entitlements, "datahub.dataset_groups": ["basic.v1"], "datahub.monthly_credits": 1000, "datahub.history_depth_days": 365, "desktop.device_limit": 1, "cloud_ai.concurrent_jobs": 1 } },
      { ...base, code: "desktop_pro", name_zh: "Desktop Pro", price_cny_fen: 26800, monthly_credits: 300, sort_order: 2, entitlements: { ...base.entitlements, "datahub.dataset_groups": ["basic.v1"], "datahub.monthly_credits": 10000, "datahub.history_depth_days": 1825, "desktop.device_limit": 1, "cloud_ai.concurrent_jobs": 2 } },
      { ...base, code: "data_developer", name_zh: "Data Pro", price_cny_fen: 39800, monthly_credits: 700, sort_order: 3, entitlements: { ...base.entitlements, "datahub.dataset_groups": ["basic.v1", "market.v1", "finance.v1"], "datahub.monthly_credits": 100000, "datahub.history_depth_days": 3650, "desktop.device_limit": 2, "cloud_ai.concurrent_jobs": 3 } },
      { ...base, code: "pro_bundle", name_zh: "Pro Bundle", price_cny_fen: 51800, monthly_credits: 1200, sort_order: 4, entitlements: { ...base.entitlements, "datahub.dataset_groups": ["basic.v1", "market.v1", "finance.v1", "pro.v1"], "datahub.monthly_credits": 150000, "datahub.history_depth_days": 7300, "desktop.device_limit": 3, "cloud_ai.concurrent_jobs": 4 } },
    ]);
  });

  it("presents plans as one progressive ladder with a single recommended tier", async () => {
    render(<MemoryRouter><PricingPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "从体验到专业研究，权益逐级增加" })).toBeInTheDocument();
    expect(screen.getAllByText("包含上一档全部权益")).toHaveLength(3);
    expect(screen.getAllByText("进阶推荐")).toHaveLength(1);
    expect(screen.getAllByText("最高配置")).toHaveLength(1);
    expect(screen.getByRole("table", { name: "完整权益对比" })).toBeInTheDocument();
    expect(screen.getByText("AI 研究月度用量")).toBeInTheDocument();
  });
});
