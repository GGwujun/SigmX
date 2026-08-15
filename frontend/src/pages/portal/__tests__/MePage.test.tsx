import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MePage } from "../MePage";

const productApi = vi.hoisted(() => ({
  getMyEntitlements: vi.fn(),
  getMyCredits: vi.fn(),
  getDataCreditBalance: vi.fn(),
  getDataHubUsage: vi.fn(),
  listDevices: vi.fn(),
}));
const cloudApi = vi.hoisted(() => ({
  listQueries: vi.fn(), listWatchlist: vi.fn(), listReports: vi.fn(),
  removeWatchlist: vi.fn(), revokeReport: vi.fn(),
}));

vi.mock("@/lib/productApi", () => productApi);
vi.mock("@/lib/cloudResearchApi", () => ({ cloudResearchApi: cloudApi }));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <MePage />
    </MemoryRouter>,
  );
}

describe("MePage", () => {
  beforeEach(() => {
    productApi.getMyEntitlements.mockReset().mockResolvedValue({
      plan_code: "pro",
      valid_from: "2026-08-01",
      valid_until: "2026-11-01",
      entitlements: {
        "desktop.device_limit": 3,
        "datahub.monthly_credits": 150000,
      },
    });
    productApi.getMyCredits.mockReset().mockResolvedValue({
      available: 900,
      expiring_soon: 200,
    });
    productApi.getDataCreditBalance.mockReset().mockResolvedValue({
      available: 149880,
      expiring_soon: 0,
    });
    productApi.getDataHubUsage.mockReset().mockResolvedValue({
      total_requests: 120,
      successful_requests: 118,
      credits_charged: 120,
      by_endpoint: [],
    });
    productApi.listDevices.mockReset().mockResolvedValue([
      {
        id: "d1",
        name: "Research PC",
        created_at: "2026-08-01T00:00:00Z",
        revoked_at: null,
      },
    ]);
    cloudApi.listQueries.mockReset().mockResolvedValue([{ id: "q1", query: "低估值 高股息", result_summary: { matches: 2 }, created_at: "2026-08-15T00:00:00Z" }]);
    cloudApi.listWatchlist.mockReset().mockResolvedValue([{ symbol: "600519.SH", name: "贵州茅台", created_at: "2026-08-15T00:00:00Z" }]);
    cloudApi.listReports.mockReset().mockResolvedValue([{ id: "r1", slug: "public-report", title: "贵州茅台简析", summary: "摘要", created_at: "2026-08-15T00:00:00Z", revoked_at: null }]);
  });

  it("renders real personal cloud assets instead of planning placeholders", async () => {
    renderPage();
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    expect(screen.getByText("低估值 高股息")).toBeInTheDocument();
    expect(screen.getByText("贵州茅台简析")).toBeInTheDocument();
    expect(screen.queryByText("规划中")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /打开公开快照/ })).toHaveAttribute("href", "/research/public-report");
  });

  it("shows the existing cloud product status and next actions", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "我的 SigmX" })).toBeInTheDocument();
    expect(screen.getByText("pro")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("149,880")).toBeInTheDocument();
    expect(screen.getByText(/120 次调用，已扣 120/)).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /管理账户/ })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("link", { name: /下载 Desktop/ })).toHaveAttribute("href", "/download");
  });

  it("keeps successful product cards visible when one status API fails", async () => {
    productApi.getDataHubUsage.mockRejectedValueOnce(new Error("usage unavailable"));

    renderPage();

    expect(await screen.findByText("部分产品状态暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("pro")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("149,880")).toBeInTheDocument();
  });
});
