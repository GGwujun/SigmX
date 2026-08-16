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
      ? Promise.resolve(ok({ code: "600519.SH", name: "贵州茅台", industry: "白酒", market: "主板", close: 1500, pe_ttm: 24, pb: 8, dividend_yield: 2, total_market_value: 1900000, as_of: "20260814", source: "local_market_store", is_delayed: true, quote: { close: 1500, rise_rate: 1.2 }, finance: { roe: 31.2, eps: 62.1 }, capital_flows: [{ trade_date: "20260814", main_net: 120000000 }], events: [{ event_date: "20260813", title: "2026 年半年度报告", category: "定期报告", url: "https://example.test/a" }], risks: ["估值需结合盈利增速验证"], research_summary: "贵州茅台盈利质量较高，需继续验证估值。", quality: { status: "verified", source: "tushare", updated_at: "2026-08-15T10:00:00+08:00" } }))
      : Promise.resolve(ok({ code: "510300", name: "沪深300ETF", fund_type: "ETF", close: 4.21, change_percent: 0.5, as_of: "20260814", source: "local_market_store", is_delayed: true, premium: { premium_rate: 0.24, nav: 4.2 }, scale: { total_size: 210000000000 }, liquidity: { amount: 1500000000, assessment: "充足" }, risks: ["指数波动风险"], research_summary: "沪深300ETF规模与流动性充足。", quality: { status: "verified", source: "local_market_store", updated_at: "2026-08-15T10:00:00+08:00" } })));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<MemoryRouter initialEntries={["/stock/600519"]}><Routes><Route path="/stock/:code" element={<PublicInstrumentPage kind="stock" />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "研究摘要" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "资金动向" })).toBeInTheDocument();
    expect(screen.getByText("2026 年半年度报告")).toBeInTheDocument();
    unmount();
    render(<MemoryRouter initialEntries={["/fund/510300"]}><Routes><Route path="/fund/:code" element={<PublicInstrumentPage kind="fund" />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("沪深300ETF")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "折溢价与净值" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "规模与流动性" })).toBeInTheDocument();
  });

  it("creates an opaque instrument handoff before exposing a Desktop link", async () => {
    window.localStorage.setItem("sigmx_auth_token", "jwt");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({ code: "600519.SH", name: "贵州茅台", industry: "白酒", market: "主板", close: 1500, pe_ttm: 24, pb: 8, dividend_yield: 2, total_market_value: 1900000, as_of: "20260814", source: "local_market_store", is_delayed: true, quote: { close: 1500 }, finance: {}, capital_flows: [], events: [], risks: ["公开数据为延迟数据"], research_summary: "贵州茅台公开研究摘要。", quality: { status: "verified", source: "tushare", updated_at: "2026-08-15T10:00:00+08:00" } }))
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

  it("renders a market-question answer instead of a false empty result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({
      query: "今天市场怎么样", intent: "market_question", interpretation: ["识别为市场概览问题"],
      answer: "20260814 可用样本 5310 个，上涨 3102 个，下跌 2058 个。", resources: [], items: [],
      source: "local_market_store", is_delayed: true,
    })));
    render(<MemoryRouter initialEntries={["/query/%E4%BB%8A%E5%A4%A9%E5%B8%82%E5%9C%BA%E6%80%8E%E4%B9%88%E6%A0%B7"]}><Routes><Route path="/query/:id" element={<PublicSearchPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText(/可用样本 5310/)).toBeInTheDocument();
    expect(screen.queryByText("当前数据中没有匹配结果，请调整条件。")).not.toBeInTheDocument();
  });

  it("routes fund results and API documentation resources to the right product page", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({
        query: "沪深300 ETF", intent: "fund_search", interpretation: ["识别为 ETF/LOF/基金搜索"], answer: null, resources: [],
        items: [{ code: "510300", name: "沪深300ETF", instrument_type: "fund", industry: "ETF", close: 4.21, pe_ttm: null, pb: null, dividend_yield: null, total_market_value: null, as_of: "20260814" }],
        source: "local_market_store", is_delayed: true,
      }))
      .mockResolvedValueOnce(ok({
        query: "Data Hub 股票日线接口", intent: "api_docs", interpretation: ["识别为 Data Hub 文档问题"], answer: "请查看接口文档。",
        resources: [{ title: "股票日线接口", url: "/docs/data-hub/stocks-daily", description: "历史日线、复权与质量字段" }], items: [],
        source: "local_market_store", is_delayed: true,
      }));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<MemoryRouter initialEntries={["/query/%E6%B2%AA%E6%B7%B1300%20ETF"]}><Routes><Route path="/query/:id" element={<PublicSearchPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /沪深300ETF/ })).toHaveAttribute("href", "/fund/510300");
    unmount();
    render(<MemoryRouter initialEntries={["/query/Data%20Hub%20%E8%82%A1%E7%A5%A8%E6%97%A5%E7%BA%BF%E6%8E%A5%E5%8F%A3"]}><Routes><Route path="/query/:id" element={<PublicSearchPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /股票日线接口/ })).toHaveAttribute("href", "/docs/data-hub/stocks-daily");
  });

  it("records an authenticated query execution in personal history", async () => {
    window.localStorage.setItem("sigmx_auth_token", "jwt");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({ query: "低估值", intent: "screener", interpretation: ["市盈率 0-20"], answer: null, resources: [], items: [{ code: "000001.SZ", name: "平安银行", instrument_type: "stock", industry: "银行", close: 12, pe_ttm: 6, pb: 0.7, dividend_yield: 5, total_market_value: 230000, as_of: "20260814" }], source: "local_market_store", is_delayed: true }))
      .mockResolvedValueOnce(ok({ id: "e1", condition_version: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter initialEntries={["/query/%E4%BD%8E%E4%BC%B0%E5%80%BC"]}><Routes><Route path="/query/:id" element={<PublicSearchPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText("平安银行")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/cloud/query-executions");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({ query: "低估值", intent: "screener", result_count: 1 });
  });
});
