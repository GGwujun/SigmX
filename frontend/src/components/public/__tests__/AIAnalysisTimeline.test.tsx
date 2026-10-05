import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.getByTestId("conversation-stream")).toHaveClass("max-w-[760px]", "space-y-6");
  });

  it("renders model replies, tool activity, and continued replies in Agent order", () => {
    const turn: ResearchConversationTurn = { task, result: null, events: [
      { id: 1, type: "assistant_delta", payload: { segment_id: "s1", delta: "我先核验行情。", iter: 1 } },
      { id: 2, type: "tool_call", payload: { tool: "search_market_data", iter: 1 } },
      { id: 3, type: "tool_result", payload: { tool: "search_market_data", status: "ok", evidence_count: 8 } },
      { id: 4, type: "assistant_delta", payload: { segment_id: "s2", delta: "行情已经拿到，继续分析财务质量。", iter: 2 } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);

    const process = screen.getByRole("button", { name: /分析过程，进行中/ });
    const firstReply = screen.getByText("我先核验行情。");
    const tool = screen.getByText("查询研究数据");
    const secondReply = screen.getByText("行情已经拿到，继续分析财务质量。");
    expect(process).toHaveAttribute("aria-expanded", "true");
    expect(firstReply.compareDocumentPosition(tool) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(tool.compareDocumentPosition(secondReply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps all live model and tool activity in one analysis-process thread", () => {
    const turn: ResearchConversationTurn = { task, result: null, events: [
      { id: 1, type: "assistant_delta", payload: { segment_id: "s1", delta: "开始核验。" } },
      { id: 2, type: "tool_call", payload: { tool: "load_research_skill" } },
      { id: 3, type: "tool_result", payload: { tool: "load_research_skill", status: "ok" } },
      { id: 4, type: "tool_call", payload: { tool: "search_market_data" } },
      { id: 5, type: "tool_result", payload: { tool: "search_market_data", status: "ok", evidence_count: 8 } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);

    expect(screen.getAllByRole("button", { name: /分析过程/ })).toHaveLength(1);
    expect(screen.getByText("加载研究方法")).toBeInTheDocument();
    expect(screen.getByText("查询研究数据")).toBeInTheDocument();
  });

  it("collapses the analysis process after a final answer is available", () => {
    const completed = { ...task, status: "succeeded" };
    const turn: ResearchConversationTurn = { task: completed, result, events: [
      { id: 1, type: "assistant_delta", payload: { segment_id: "s1", delta: "正在核验行情与估值。" } },
      { id: 2, type: "tool_call", payload: { tool: "search_market_data" } },
      { id: 3, type: "tool_result", payload: { tool: "search_market_data", status: "ok", evidence_count: 8 } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);

    const process = screen.getByRole("button", { name: /分析过程，已完成/ });
    expect(process).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("正在核验行情与估值。")).not.toBeInTheDocument();
    expect(screen.getByText(result.summary)).toBeInTheDocument();
    fireEvent.click(process);
    expect(screen.getByText("正在核验行情与估值。")).toBeInTheDocument();
  });

  it("never renders raw thinking or final JSON deltas", () => {
    const turn: ResearchConversationTurn = { task, result: null, events: [
      { id: 1, type: "thinking_delta", payload: { delta: "internal English reasoning" } },
      { id: 2, type: "text_delta", payload: { delta: "{\"summary\":\"raw JSON\"}" } },
      { id: 3, type: "assistant_delta", payload: { segment_id: "safe", delta: "正在核验公开数据。" } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);
    expect(screen.getByText("正在核验公开数据。")).toBeInTheDocument();
    expect(screen.queryByText(/internal English reasoning|raw JSON/)).not.toBeInTheDocument();
  });

  it("shows a streaming cursor on the latest live assistant segment", () => {
    const turn: ResearchConversationTurn = { task, result: null, events: [
      { id: 1, type: "assistant_delta", payload: { segment_id: "live", delta: "正在分析最新数据。" } },
    ] };
    render(<MemoryRouter><AIAnalysisTimeline {...base} turns={[turn]} /></MemoryRouter>);
    expect(screen.getByTestId("assistant-streaming-cursor")).toBeInTheDocument();
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
