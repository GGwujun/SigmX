import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PublicInstrumentPage } from "../PublicInstrumentPage";
import { PublicReportPage } from "../PublicReportPage";
import { PublicSearchPage } from "../PublicSearchPage";


function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("public discovery funnel", () => {
  it("shows real limited search results and preserves save intent for login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({
      query: "低估值 高股息", interpretation: ["市盈率 0-20", "股息率 ≥ 3%"],
      items: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 12, pe_ttm: 6, pb: 0.7, dividend_yield: 5, total_market_value: 230000, as_of: "20260814" }],
      source: "local_market_store", is_delayed: true,
    })));
    render(<MemoryRouter initialEntries={["/query/%E4%BD%8E%E4%BC%B0%E5%80%BC%20%E9%AB%98%E8%82%A1%E6%81%AF"]}><Routes><Route path="/query/:id" element={<PublicSearchPage />} /><Route path="/login" element={<div>登录页</div>} /></Routes></MemoryRouter>);
    expect(await screen.findByText("平安银行")).toBeInTheDocument();
    expect(screen.getByText(/延迟数据/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存查询" }));
    expect(await screen.findByText("登录页")).toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem("sigmx_pending_saved_query") || "{}")).toMatchObject({ query: "低估值 高股息" });
  });

  it("renders stock and fund summaries from public APIs", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => url.includes("/stocks/")
      ? Promise.resolve(ok({ code: "600519.SH", name: "贵州茅台", industry: "白酒", market: "主板", close: 1500, pe_ttm: 24, pb: 8, dividend_yield: 2, total_market_value: 1900000, as_of: "20260814", source: "local_market_store", is_delayed: true }))
      : Promise.resolve(ok({ code: "510300", name: "沪深300ETF", fund_type: "ETF", close: 4.21, change_percent: 0.5, as_of: "20260814", source: "local_market_store", is_delayed: true })));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<MemoryRouter initialEntries={["/stock/600519"]}><Routes><Route path="/stock/:code" element={<PublicInstrumentPage kind="stock" />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    unmount();
    render(<MemoryRouter initialEntries={["/fund/510300"]}><Routes><Route path="/fund/:code" element={<PublicInstrumentPage kind="fund" />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("沪深300ETF")).toBeInTheDocument();
  });

  it("creates an opaque instrument handoff before exposing a Desktop link", async () => {
    window.localStorage.setItem("sigmx_auth_token", "jwt");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({ code: "600519.SH", name: "贵州茅台", industry: "白酒", market: "主板", close: 1500, pe_ttm: 24, pb: 8, dividend_yield: 2, total_market_value: 1900000, as_of: "20260814", source: "local_market_store", is_delayed: true }))
      .mockResolvedValueOnce(ok({ id: "h1", token: "sxrh_abc", deep_link: "sigmx://research/sxrh_abc", expires_at: "2026-08-15T00:10:00Z" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter initialEntries={["/stock/600519"]}><Routes><Route path="/stock/:code" element={<PublicInstrumentPage kind="stock" />} /></Routes></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "在 Desktop 中继续研究" }));
    expect(await screen.findByRole("link", { name: "打开 Desktop" })).toHaveAttribute("href", "sigmx://research/sxrh_abc");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ kind: "instrument", payload: { symbol: "600519.SH" } });
  });

  it("shows an explicit revoked state for a shared report", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 410, json: async () => ({ detail: "report has been revoked" }) } as Response));
    render(<MemoryRouter initialEntries={["/research/revoked"]}><Routes><Route path="/research/:slug" element={<PublicReportPage />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("该报告已被作者撤销")).toBeInTheDocument());
  });
});
