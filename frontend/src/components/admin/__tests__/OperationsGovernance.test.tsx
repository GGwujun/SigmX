import { render, screen, waitFor } from "@testing-library/react";
import { OperationsGovernance } from "../OperationsGovernance";

vi.mock("@/lib/productApi", () => ({
  getOperationsState: vi.fn().mockResolvedValue({
    products: [{ code: "desktop_pro", enabled: true, price_cny_fen: 26800, updated_at: "now" }],
    endpoints: [{ code: "market.daily", enabled: true, credit_cost: 3, unit_cost_cny_fen: 1.2, quality_score: 0.998, updated_at: "now" }],
    content: [{ slot: "home.hero", title: "AI 选股", href: "/query", enabled: true, updated_at: "now" }], refunds: [],
    metrics: { desktop_research_users: 12, desktop_active_sessions: 18, usage_revenue_cny_fen: 3000, usage_cost_cny_fen: 1200, gross_margin_rate: 0.6 },
    audit: [{ id: "a1", actor_id: "admin", object_type: "endpoint", object_id: "market.daily", action: "upsert", reason: "接口成本校准", before: {}, after: {}, created_at: "now" }],
  }),
  updateOperationalProduct: vi.fn(), updateOperationalEndpoint: vi.fn(), updateOperationalContent: vi.fn(), refundActivationOrder: vi.fn(),
}));

it("shows product, endpoint, content, desktop and margin operations", async () => {
  render(<OperationsGovernance />);
  await waitFor(() => expect(screen.getAllByText(/market\.daily/).length).toBeGreaterThan(0));
  expect(screen.getByText("Desktop 研究用户")).toBeInTheDocument();
  expect(screen.getByText("60.0%")).toBeInTheDocument();
  expect(screen.getByText("商品与价格")).toBeInTheDocument();
  expect(screen.getByText("内容与增长位")).toBeInTheDocument();
  expect(screen.getByText("接口成本与质量")).toBeInTheDocument();
  expect(screen.getByText("订单撤销 / 退款记录")).toBeInTheDocument();
});
