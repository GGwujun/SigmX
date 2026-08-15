import { describe, it, expect, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { OrdersPage } from "../OrdersPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(...bodies: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => {
      const body = bodies.shift();
      return { ok: true, status: 200, json: async () => body } as unknown as Response;
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OrdersPage />
    </MemoryRouter>,
  );
}

describe("OrdersPage", () => {
  it("renders the order history", async () => {
    mockFetch({
      items: [
        {
          id: "o1",
          plan_code: "desktop_pro",
          status: "paid",
          channel: "activation_code",
          months: 3,
          created_at: "2026-08-14T10:00:00+00:00",
          paid_at: "2026-08-14T10:00:00+00:00",
        },
      ],
    }, { plans: [{ code: "desktop_pro", name_zh: "桌面专业研究版" }] });
    renderPage();
    expect(await screen.findByText("桌面专业研究版")).toBeInTheDocument();
    expect(screen.getByText("已支付")).toBeInTheDocument();
    expect(screen.getByText("3 个月")).toBeInTheDocument();
  });

  it("shows the empty state when there are no orders", async () => {
    mockFetch({ items: [] }, { plans: [] });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/暂无订单/)).toBeInTheDocument();
    });
  });
});
