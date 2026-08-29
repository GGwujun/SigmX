import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AIAnalysisTimeline } from "../AIAnalysisTimeline";
import type { ResearchConversationTurn, ResearchResult, ResearchTask } from "@/lib/researchApi";

const question = "寻找低估值且高股息的 A 股公司";
const task: ResearchTask = { id: "task-1", user_id: "u1", question, template_id: null, scope: {}, constraints: [], status: "running", steps: [{ key: "scan", label: "筛选市场候选", status: "running" }], error: null, created_at: "2026-08-28T08:00:00Z", started_at: null, finished_at: null };
const result: ResearchResult = { task_id: "task-1", question, template_id: null, summary: "筛得 1 家符合条件的公司。", source: "local", as_of: "2026-08-21", scope: {}, risks: [], created_at: "2026-08-28T08:01:00Z", model: "glm-5.1", candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: .6, dividend_yield: 5, total_market_value: 2173, reason: "估值较低且股息率较高", evidence: [] }] };
const base = { turns: [] as ResearchConversationTurn[], pendingQuestion: "", planning: false, pendingError: "", loadError: "", onRetry: vi.fn() };

describe("AIAnalysisTimeline", () => {
  it("welcomes the user without technical connection details", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "今天想分析什么？" })).toBeInTheDocument();
    expect(screen.queryByText(/glm|模型|provider|API/i)).not.toBeInTheDocument();
  });

  it("shows a sent question and immediately starts analysis without a plan", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} pendingQuestion={question} planning /></MemoryRouter>);
    expect(screen.getByText(question)).toBeInTheDocument();
    expect(screen.getByText("正在理解你的问题")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "研究计划" })).not.toBeInTheDocument();
  });

  it("turns real runtime events into a single safe status line", () => {
    const turn: ResearchConversationTurn = { task, result: null, events: [
      { id: 1, type: "running", payload: {} },
      { id: 2, type: "tool_call", payload: { tool: "secret_stock_tool", api_url: "https://secret" } },
      { id: 3, type: "tool_result", payload: { tool: "secret_stock_tool", evidence_count: 8 } },
      { id: 4, type: "llm_usage", payload: { model: "glm-5.1" } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);
    expect(screen.getByText("正在整理和分析数据")).toBeInTheDocument();
    // GPT-style: no plan step list, no activity history — only the latest status
    expect(screen.queryByText("筛选市场候选")).not.toBeInTheDocument();
    expect(screen.queryByText("正在查询研究数据")).not.toBeInTheDocument();
    expect(screen.queryByText("已获取一批可用数据")).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_stock_tool|https:\/\/secret|glm-5.1/)).not.toBeInTheDocument();
  });

  it("renders results inline and keeps multiple restored turns in one chat", () => {
    const followUpTask = { ...task, id: "task-2", question: "再比较一下银行板块", status: "succeeded" };
    const followUpResult = { ...result, task_id: "task-2", question: followUpTask.question, summary: "银行板块中它的估值仍处于较低位置。", candidates: [] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[{ task: { ...task, status: "succeeded" }, events: [], result }, { task: followUpTask, events: [], result: followUpResult }]} /></MemoryRouter>);
    expect(screen.getByText(question)).toBeInTheDocument();
    expect(screen.getByText("再比较一下银行板块")).toBeInTheDocument();
    expect(screen.getByText(result.summary)).toBeInTheDocument();
    expect(screen.getByText(followUpResult.summary)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /平安银行/ })).toHaveAttribute("href", "/stock/000001.SZ");
    expect(screen.queryByRole("link", { name: "查看完整分析" })).not.toBeInTheDocument();
  });

  it("offers recovery after a failed analysis", () => {
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[{ task: { ...task, status: "failed", error: "请求失败（500）" }, events: [], result: null }]} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "分析没有完成" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新尝试" })).toBeInTheDocument();
  });
});
