import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "../LandingPage";

const discovery = { as_of: "2026-08-21", source: "local_market_store", is_delayed: true, market_status: "closed", metrics: [
  { key: "shanghai", label: "上证指数", value: 3825.76, change: 0.42, unit: null, quality: "available", secondary_value: null },
  { key: "breadth", label: "上涨家数", value: null, change: null, unit: "家", quality: "unavailable", secondary_value: null },
], templates: [{ id: "dividend", label: "低估值高股息", description: "估值与分红交叉筛选", prompt: "寻找低估值且高股息的 A 股公司", data_domains: ["估值", "分红"] }] };
const task = { id: "task-real-1", user_id: "user-1", question: discovery.templates[0].prompt, template_id: "dividend", scope: { market: "A股" }, constraints: [], status: "succeeded", error: null, steps: [{ key: "interpret", label: "解析研究条件", status: "succeeded" }], created_at: "2026-08-24T10:00:00Z", started_at: "2026-08-24T10:00:00Z", finished_at: "2026-08-24T10:00:01Z" };
const result = { task_id: task.id, question: task.question, template_id: "dividend", summary: "基于本地市场数据筛得 1 个候选。", source: "local_market_store", as_of: "2026-08-21", scope: { market: "A股" }, candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: 0.6, dividend_yield: 5, total_market_value: 2173, reason: "PE 6；股息率 5%", evidence: [{ field: "pe_ttm", value: 6, source: "local_market_store", as_of: "2026-08-21" }] }], risks: ["数据可能存在延迟"], created_at: "2026-08-24T10:00:01Z" };

describe("LandingPage real research flow", () => {
  beforeEach(() => {
    localStorage.setItem("sigmx_auth_token", "jwt-token");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/public/discovery") return new Response(JSON.stringify(discovery), { status: 200 });
      if (url === "/api/research/tasks" && init?.method === "POST") return new Response(JSON.stringify(task), { status: 201 });
      if (url === "/api/research/tasks/task-real-1/result") return new Response(JSON.stringify(result), { status: 200 });
      return new Response("not found", { status: 404 });
    }));
  });
  afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

  it("renders server values and unavailable states without demo labels", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    expect(await screen.findByText("3,825.76")).toBeInTheDocument();
    expect(screen.getByText("暂无数据")).toBeInTheDocument();
    expect(screen.queryByText(/演示数据/)).not.toBeInTheDocument();
    expect(screen.getByText(/数据日期 2026-08-21/)).toBeInTheDocument();
  });

  it("runs a persisted server task from a server template", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /低估值高股息/ }));
    expect(screen.getByLabelText("研究问题")).toHaveValue(discovery.templates[0].prompt);
    fireEvent.click(screen.getByRole("button", { name: "运行研究" }));
    expect(await screen.findByRole("heading", { name: "研究计划" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "开始执行" }));
    expect(await screen.findByText("平安银行")).toBeInTheDocument();
    expect(screen.getByText(result.summary)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看完整结果" })).toHaveAttribute("href", "/research/result/task-real-1");
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/research/tasks", expect.objectContaining({ method: "POST" })));
  });
});
