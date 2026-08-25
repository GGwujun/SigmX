import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DataHubDocsPage } from "../DataHubDocsPage";

afterEach(() => vi.restoreAllMocks());

const items = [
  { endpoint_code: "stocks.daily", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/stocks/daily", dataset_group: "market.v1", pricing_mode: "per_unit", base_cost: 1, unit_name: "row", unit_size: 100, unit_cost: 1, max_cost: 100, enabled: true },
  { endpoint_code: "stocks.moneyflow", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/stocks/moneyflow", dataset_group: "capital.v1", pricing_mode: "per_unit", base_cost: 2, unit_name: "row", unit_size: 100, unit_cost: 2, max_cost: 100, enabled: true },
  { endpoint_code: "news.finance_rss_summary", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/news/finance-rss-summary", dataset_group: "market.v1", pricing_mode: "per_unit", base_cost: 1, unit_name: "row", unit_size: 100, unit_cost: 1, max_cost: 100, enabled: true },
  { endpoint_code: "macro.indicators", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/macro/indicators", dataset_group: "macro.v1", pricing_mode: "per_unit", base_cost: 1, unit_name: "row", unit_size: 100, unit_cost: 1, max_cost: 100, enabled: true },
  { endpoint_code: "boards.daily", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/boards/daily", dataset_group: "market.v1", pricing_mode: "per_unit", base_cost: 2, unit_name: "rows", unit_size: 1000, unit_cost: 1, max_cost: 100, enabled: true },
];

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

it("renders a category, endpoint list, and endpoint-detail workspace", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items }) } as Response));
  render(<MemoryRouter><DataHubDocsPage /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "股票日线行情" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "接口分类" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "接口列表" })).toBeInTheDocument();
  expect(screen.getByRole("article", { name: "接口详情" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "股票日线行情" })).toBeInTheDocument();
  expect(screen.getByText("请求参数")).toBeInTheDocument();
  expect(screen.getByText("返回字段")).toBeInTheDocument();
});

it("classifies catalog endpoints by endpoint semantics when the dataset group is generic", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items }) } as Response));
  render(<MemoryRouter><DataHubDocsPage /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: /公告资讯/ }));
  expect(screen.getByRole("button", { name: /news.finance_rss_summary/ })).toBeInTheDocument();
});

it("selects an endpoint and synchronizes the detail URL", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items }) } as Response));
  render(<MemoryRouter initialEntries={["/docs/data-hub/"]}><DataHubDocsPage /><LocationProbe /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: /资金流/ }));
  fireEvent.click(screen.getByRole("button", { name: /个股资金流向/ }));
  expect(screen.getByRole("heading", { name: "个股资金流向" })).toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent("/docs/data-hub/capital/stocks.moneyflow");
});

it("uses category-specific parameters for macro data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items }) } as Response));
  render(<MemoryRouter><DataHubDocsPage /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: /宏观行业/ }));
  expect(screen.getAllByText("indicator_code").length).toBeGreaterThan(0);
  expect(screen.getByText(/宏观或行业指标代码/)).toBeInTheDocument();
  expect(screen.queryByText(/证券代码，例如 600519/)).not.toBeInTheDocument();
});

it("uses the registered endpoint contract instead of guessing parameters from its category", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items }) } as Response));
  render(<MemoryRouter initialEntries={["/docs/data-hub/macro/boards.daily"]}><DataHubDocsPage /></MemoryRouter>);
  await screen.findByRole("heading", { name: "板块日线行情" });
  expect(screen.getAllByText("board_code").length).toBeGreaterThan(0);
  expect(screen.getByText(/板块代码，例如 BK0001/)).toBeInTheDocument();
  expect(screen.queryByText("indicator_code")).not.toBeInTheDocument();
  expect(screen.getByText(/board_code=BK0001/)).toBeInTheDocument();
});

it("runs the selected endpoint from the docs and reports request metadata", async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url === "/api/datahub/catalog") return Promise.resolve({ ok: true, status: 200, json: async () => ({ items }) } as Response);
    if (url === "/api/v1/stocks/daily?symbol=600519.SH&limit=10") {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "X-Request-ID": "req-docs-1", "X-DataHub-Credits-Charged": "2" }),
        text: async () => '{"data":[]}',
      } as Response);
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><DataHubDocsPage /></MemoryRouter>);

  await screen.findByRole("heading", { name: "股票日线行情" });
  fireEvent.click(screen.getByRole("button", { name: "在线调试" }));
  expect(screen.getByLabelText("Credential")).toHaveAttribute("autocomplete", "new-password");
  fireEvent.change(screen.getByLabelText("Credential"), { target: { value: "sxd_live_docs_only" } });
  fireEvent.change(screen.getByLabelText("symbol 参数"), { target: { value: "600519.SH" } });
  fireEvent.change(screen.getByLabelText("limit 参数"), { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "发送请求" }));

  expect(await screen.findByText("HTTP 200")).toBeInTheDocument();
  expect(screen.getByText("req-docs-1")).toBeInTheDocument();
  expect(screen.getByText("2 Data Credit")).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/stocks/daily?symbol=600519.SH&limit=10",
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer sxd_live_docs_only" }) }),
  ));
  expect(JSON.stringify(localStorage)).not.toContain("sxd_live_docs_only");
});
