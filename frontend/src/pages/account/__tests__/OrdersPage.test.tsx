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
          price_cny_fen: 26800,
          months: 3,
          created_at: "2026-08-14T10:00:00+00:00",
          paid_at: "2026-08-14T10:00:00+00:00",
        },
      ],
    }, { plans: [{ code: "desktop_pro", name_zh: "桌面专业研究版" }] }, {
      period_days: 30, paid_orders: 1, paid_cny_fen: 26800,
      research_credits_consumed: 70, data_credits_consumed: 120,
      daily: [{ date: "2026-08-14", research_credits_consumed: 70, data_credits_consumed: 120, paid_cny_fen: 26800 }],
    }, { items: [{ code: "data_10k", name_zh: "Data Credit 10,000" }] });
    renderPage();
    expect(await screen.findByText("桌面专业研究版")).toBeInTheDocument();
    expect(screen.getByText("已支付")).toBeInTheDocument();
    expect(screen.getByText("3 个月")).toBeInTheDocument();
    expect(screen.getAllByText("¥268.00")).toHaveLength(2);
    expect(screen.getByText("套餐内研究额度消耗")).toBeInTheDocument();
    expect(screen.getByText("套餐内数据调用额度消耗")).toBeInTheDocument();
  });

  it("shows the empty state when there are no orders", async () => {
    mockFetch({ items: [] }, { plans: [] }, {
      period_days: 30, paid_orders: 0, paid_cny_fen: 0,
      research_credits_consumed: 0, data_credits_consumed: 0, daily: [],
    }, { items: [] });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/暂无订单/)).toBeInTheDocument();
    });
  });
});
