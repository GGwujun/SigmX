import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchResultPage } from "../ResearchResultPage";

describe("ResearchResultPage", () => {
  afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });
  it("loads the persisted result identified by task id", async () => {
    localStorage.setItem("sigmx_auth_token", "jwt-token");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ task_id: "task-real-1", question: "寻找低估值且高股息的 A 股公司", template_id: "dividend", summary: "基于真实市场库筛得 1 个候选。", source: "local_market_store", as_of: "2026-08-21", scope: { market: "A股" }, candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: 0.6, dividend_yield: 5, total_market_value: 2173, reason: "PE 6；股息率 5%", evidence: [{ field: "pe_ttm", value: 6, source: "local_market_store", as_of: "2026-08-21" }] }], risks: ["数据可能存在延迟"], created_at: "2026-08-24T10:00:01Z" }), { status: 200 })));
    render(<MemoryRouter initialEntries={["/research/result/task-real-1"]}><Routes><Route path="/research/result/:taskId" element={<ResearchResultPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "寻找低估值且高股息的 A 股公司" })).toBeInTheDocument();
    expect(screen.getByText("基于真实市场库筛得 1 个候选。")).toBeInTheDocument();
    expect(screen.getByText("数据日期 2026-08-21")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /平安银行/ })).toHaveAttribute("href", "/stock/000001.SZ");
    expect(screen.getByText("市盈率（TTM）")).toBeInTheDocument();
    expect(screen.getByText("6.00 倍")).toBeInTheDocument();
    expect(screen.getByText("来源：local_market_store")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "使用该问题再次研究" })).toHaveAttribute("href", "/?q=%E5%AF%BB%E6%89%BE%E4%BD%8E%E4%BC%B0%E5%80%BC%E4%B8%94%E9%AB%98%E8%82%A1%E6%81%AF%E7%9A%84%20A%20%E8%82%A1%E5%85%AC%E5%8F%B8");
    expect(fetch).toHaveBeenCalledWith("/api/research/tasks/task-real-1/result", expect.objectContaining({ headers: { Authorization: "Bearer jwt-token" } }));
  });
});
