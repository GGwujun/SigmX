import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProductStatus } from "../ProductStatus";
import * as productApi from "@/lib/productApi";

vi.mock("@/lib/productApi", () => ({ getMyEntitlements: vi.fn(), getMyCredits: vi.fn(), getPlans: vi.fn() }));

describe("ProductStatus", () => {
  it("shows the current plan in the progressive ladder without leaking its internal code", async () => {
    vi.mocked(productApi.getMyEntitlements).mockResolvedValue({ plan_code: "data_developer", valid_from: null, valid_until: null, entitlements: { "datahub.monthly_credits": 100000, "datahub.dataset_groups": ["basic.v1", "market.v1", "finance.v1"], "datahub.history_depth_days": 3650, "desktop.device_limit": 2 } });
    vi.mocked(productApi.getMyCredits).mockResolvedValue({ available: 650, expiring_soon: 0 });
    vi.mocked(productApi.getPlans).mockResolvedValue([
      { code: "free", name_zh: "免费版", sort_order: 1 }, { code: "desktop_pro", name_zh: "Desktop Pro", sort_order: 2 }, { code: "data_developer", name_zh: "Data Pro", sort_order: 3 }, { code: "pro_bundle", name_zh: "Pro Bundle", sort_order: 4 },
    ] as never);
    render(<ProductStatus />);
    expect(await screen.findByText("Data Pro")).toBeInTheDocument();
    expect(screen.getByText("第 3/4 档")).toBeInTheDocument();
    expect(screen.getByText(/market\.v1/)).toBeInTheDocument();
    expect(screen.queryByText("data_developer")).not.toBeInTheDocument();
  });
});
