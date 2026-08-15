import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MePage } from "../MePage";

const productApi = vi.hoisted(() => ({
  getMyEntitlements: vi.fn(),
  getMyCredits: vi.fn(),
  getMyUsage: vi.fn(),
  listDevices: vi.fn(),
}));

vi.mock("@/lib/productApi", () => productApi);

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
        "datahub.daily_quota": 10000,
      },
    });
    productApi.getMyCredits.mockReset().mockResolvedValue({
      available: 900,
      expiring_soon: 200,
    });
    productApi.getMyUsage.mockReset().mockResolvedValue({
      metric: "datahub_requests",
      day: "2026-08-15",
      consumed: 120,
      quota_daily: 10000,
      remaining: 9880,
    });
    productApi.listDevices.mockReset().mockResolvedValue([
      {
        id: "d1",
        name: "Research PC",
        created_at: "2026-08-01T00:00:00Z",
        revoked_at: null,
      },
    ]);
  });

  it("shows the existing cloud product status and next actions", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "我的 SigmX" })).toBeInTheDocument();
    expect(screen.getByText("pro")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("120 / 10,000")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /管理账户/ })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("link", { name: /下载 Desktop/ })).toHaveAttribute("href", "/download");
  });

  it("keeps successful product cards visible when one status API fails", async () => {
    productApi.getMyUsage.mockRejectedValueOnce(new Error("usage unavailable"));

    renderPage();

    expect(await screen.findByText("部分产品状态暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("pro")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("暂不可用")).toBeInTheDocument();
  });
});
