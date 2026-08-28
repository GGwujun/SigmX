import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AIAnalysisTimeline } from "../AIAnalysisTimeline";
import type { ResearchPlan, ResearchResult, ResearchTask } from "@/lib/researchApi";

const plan: ResearchPlan = {
  id: "plan-1", question: "寻找低估值且高股息的 A 股公司", template_id: null,
  scope: { market: "A股" }, ranking: [], constraints: [], executable: true, suggested_question: null,
  conditions: [{ id: "c1", metric: "pe_ttm", label: "市盈率不高于 20 倍", operator: "<=", value: 20, period: null, benchmark: null, status: "supported", reason: null, alternatives: [] }],
  datasets: [{ key: "valuation", name: "估值数据", status: "supported", as_of: "2026-08-21", coverage: null }],
  steps: [{ key: "scan", label: "筛选市场候选", status: "running" }], model: "glm-5.1",
};
const task: ResearchTask = { id: "task-1", user_id: "u1", question: plan.question, template_id: null, scope: {}, constraints: [], status: "running", steps: plan.steps, error: null, created_at: "2026-08-28T08:00:00Z", started_at: null, finished_at: null };
const result: ResearchResult = { task_id: "task-1", question: plan.question, template_id: null, summary: "筛得 1 家符合条件的公司。", source: "local", as_of: "2026-08-21", scope: {}, risks: [], created_at: "2026-08-28T08:01:00Z", model: "glm-5.1", candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: .6, dividend_yield: 5, total_market_value: 2173, reason: "估值较低且股息率较高", evidence: [] }] };
const base = { question: plan.question, plan: null, task: null, events: [], result: null, loadError: "", runError: "", onRun: vi.fn(), onRetry: vi.fn(), onUseSuggested: vi.fn(), onResetPlan: vi.fn() };

describe("AIAnalysisTimeline", () => {
  it("welcomes the user without technical connection details", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="idle" /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "今天想分析什么？" })).toBeInTheDocument();
    expect(screen.queryByText(/glm|模型|provider|API/i)).not.toBeInTheDocument();
  });

  it("shows the user question and a friendly planning state", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="planning" /></MemoryRouter>);
    expect(screen.getByText(plan.question)).toBeInTheDocument();
    expect(screen.getByText("正在理解你的研究问题")).toBeInTheDocument();
  });

  it("renders a reviewable plan without its model metadata", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="plan" plan={plan} /></MemoryRouter>);
    expect(screen.getByText("我整理了一份研究计划")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "研究计划" })).toBeInTheDocument();
    expect(screen.queryByText("glm-5.1")).not.toBeInTheDocument();
  });

  it("turns runtime events into safe user-facing progress", () => {
    const events = [{ id: 1, type: "tool_started", payload: { tool: "secret_stock_tool", api_url: "https://secret" } }];
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="running" plan={plan} task={task} events={events} /></MemoryRouter>);
    expect(screen.getByText("正在分析市场数据")).toBeInTheDocument();
    expect(screen.getByText("筛选市场候选")).toBeInTheDocument();
    expect(screen.queryByText(/secret_stock_tool|https:\/\/secret/)).not.toBeInTheDocument();
  });

  it("renders result cards and full-result navigation", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="done" plan={plan} task={task} result={result} /></MemoryRouter>);
    expect(screen.getByText("筛得 1 家符合条件的公司。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /平安银行/ })).toHaveAttribute("href", "/stock/000001.SZ");
    expect(screen.getByText("PE 6")).toBeInTheDocument();
    expect(screen.getByText("股息率 5%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看完整结果" })).toHaveAttribute("href", "/research/result/task-1");
    expect(screen.queryByText("glm-5.1")).not.toBeInTheDocument();
  });

  it("offers recovery after a failed analysis", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} phase="error" runError="请求失败（500）" /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "分析没有完成" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新尝试" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "修改问题" })).toBeInTheDocument();
  });
});
