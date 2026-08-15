import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DataHubDocsPage } from "../DataHubDocsPage";

afterEach(() => vi.restoreAllMocks());

it("renders server-driven endpoint docs and personal credential examples", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items: [{ endpoint_code: "stocks.daily", catalog_version: 2, http_method: "GET", path_pattern: "/api/v1/stocks/daily", dataset_group: "market.v1", pricing_mode: "per_unit", base_cost: 1, unit_name: "row", unit_size: 100, unit_cost: 1, max_cost: 100, enabled: true }] }) } as Response));
  render(<MemoryRouter><DataHubDocsPage /></MemoryRouter>);
  expect(await screen.findByText("stocks.daily")).toBeInTheDocument();
  expect(screen.getByText(/Authorization: Bearer sxd_live_/)).toBeInTheDocument();
  expect(screen.getByText("Python SDK 示例")).toBeInTheDocument();
});
