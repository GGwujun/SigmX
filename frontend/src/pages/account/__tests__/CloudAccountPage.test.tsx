import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { CloudAccountPage } from "../CloudAccountPage";

// Each fetch returns the next queued body. Tests set the whole sequence up front
// so Promise.all ordering doesn't matter — every call gets a valid response.
function mockFetchResponses(map: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      for (const key of Object.keys(map)) {
        if (url.includes(key)) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => map[key],
          } as unknown as Response);
        }
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as unknown as Response);
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <CloudAccountPage />
    </MemoryRouter>,
  );
}

const FREE_ENT = {
  plan_code: "free",
  valid_from: null,
  valid_until: null,
  entitlements: { "desktop.device_limit": 1 },
};

describe("CloudAccountPage", () => {
  it("shows the device limit from entitlements", async () => {
    mockFetchResponses({
      "/api/devices": { items: [] },
      "/api/entitlements": FREE_ENT,
      "/api/credits/me": { available: 0, expiring_soon: 0 },
    });
    renderPage();
    expect(await screen.findByText(/套餐设备数上限：1 台/)).toBeInTheDocument();
  });

  it("approves a device via the user-code form", async () => {
    mockFetchResponses({
      "/api/devices": { items: [] },
      "/api/entitlements": FREE_ENT,
      "/api/credits/me": { available: 0, expiring_soon: 0 },
      "/api/devices/authorize/approve": { ok: true },
    });
    renderPage();
    const input = await screen.findByPlaceholderText("ABCD-EFGH");
    fireEvent.change(input, { target: { value: "wxyz-1234" } });
    fireEvent.click(screen.getByText("批准链接"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("ABCD-EFGH")).toHaveValue("");
    });
  });

  it("lists a linked device", async () => {
    mockFetchResponses({
      "/api/devices": {
        items: [
          { id: "d1", name: "我的桌面", created_at: "2026-08-14T10:00:00+00:00", revoked_at: null },
        ],
      },
      "/api/entitlements": FREE_ENT,
      "/api/credits/me": { available: 0, expiring_soon: 0 },
    });
    renderPage();
    expect(await screen.findByText("我的桌面")).toBeInTheDocument();
    expect(screen.getByText(/已链接设备（1\/1）/)).toBeInTheDocument();
  });
});
