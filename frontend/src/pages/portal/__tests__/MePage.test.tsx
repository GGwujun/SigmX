import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MePage } from "../MePage";

const productApi = vi.hoisted(() => ({
  getMyEntitlements: vi.fn(),
  getMyCredits: vi.fn(),
  getDataCreditBalance: vi.fn(),
  getDataHubUsage: vi.fn(),
  listDevices: vi.fn(),
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  getNotificationPreferences: vi.fn(),
  putNotificationPreferences: vi.fn(),
}));
const cloudApi = vi.hoisted(() => ({
  listQueries: vi.fn(), listWatchlist: vi.fn(), listReports: vi.fn(),
  removeWatchlist: vi.fn(), revokeReport: vi.fn(),
  createHandoff: vi.fn(),
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
      plan_code: "pro_bundle",
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
    productApi.listNotifications.mockReset().mockResolvedValue([{ id: "budget:k1:2026-08-15:80", kind: "budget", title: "Data Hub 预算达到 80%", body: "研究脚本今日已使用 80/100 Data Credit", read_at: null, created_at: "2026-08-15T00:00:00Z" }]);
    productApi.markNotificationRead.mockReset().mockResolvedValue(undefined);
    productApi.getNotificationPreferences.mockReset().mockResolvedValue({ budget_alerts: true, product_updates: true, cloud_tasks: true });
    productApi.putNotificationPreferences.mockReset().mockImplementation(async (value) => value);
    cloudApi.listQueries.mockReset().mockResolvedValue([{ id: "q1", query: "低估值 高股息", result_summary: { matches: 2 }, created_at: "2026-08-15T00:00:00Z" }]);
    cloudApi.listWatchlist.mockReset().mockResolvedValue([{ symbol: "600519.SH", name: "贵州茅台", created_at: "2026-08-15T00:00:00Z" }]);
    cloudApi.listReports.mockReset().mockResolvedValue([{ id: "r1", slug: "public-report", title: "贵州茅台简析", summary: "摘要", created_at: "2026-08-15T00:00:00Z", revoked_at: null }]);
    cloudApi.createHandoff.mockReset().mockResolvedValue({ id: "h1", token: "sxrh_abc", deep_link: "sigmx://research/sxrh_abc", expires_at: "2026-08-15T00:10:00Z" });
  });

  it("creates an opaque one-time Desktop handoff for a saved query", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "在 Desktop 继续：低估值 高股息" }));
    expect(await screen.findByRole("link", { name: "打开 Desktop" })).toHaveAttribute("href", "sigmx://research/sxrh_abc");
    expect(screen.getByRole("link", { name: "尚未安装？下载 Desktop" })).toHaveAttribute("href", "/download");
    expect(cloudApi.createHandoff).toHaveBeenCalledWith("saved_query", { query: "低估值 高股息", saved_query_id: "q1" });
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
    expect(screen.getByText("pro_bundle")).toBeInTheDocument();
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
    expect(screen.getByText("pro_bundle")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("149,880")).toBeInTheDocument();
  });

  it("shows personal notifications, marks them read, and updates preferences", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Data Hub 预算达到 80%/ }));
    expect(productApi.markNotificationRead).toHaveBeenCalledWith("budget:k1:2026-08-15:80");
    fireEvent.click(screen.getByLabelText("套餐与积分到账"));
    expect(productApi.putNotificationPreferences).toHaveBeenCalledWith({
      budget_alerts: true, product_updates: false, cloud_tasks: true,
    });
  });
});
