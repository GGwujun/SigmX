import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "../LandingPage";

const discovery = { as_of: "2026-08-21", source: "local_market_store", is_delayed: true, market_status: "closed", metrics: [
  { key: "shanghai", label: "上证指数", value: 3825.76, change: 0.42, unit: null, quality: "available", secondary_value: null },
  { key: "market_breadth", label: "上涨 / 下跌", value: 866, change: null, unit: "家", quality: "delayed", secondary_value: 4265 },
  { key: "turnover", label: "两市成交", value: 35.52, change: null, unit: "亿元", quality: "delayed", secondary_value: null },
], templates: [{ id: "dividend", label: "低估值高股息", description: "估值与分红交叉筛选", prompt: "寻找低估值且高股息的 A 股公司", data_domains: ["估值", "分红"] }] };
const plan = { id: "plan-1", question: discovery.templates[0].prompt, template_id: "dividend", scope: { market: "A股", exclude_st: true }, conditions: [
  { id: "c1", metric: "pe_ttm", label: "市盈率（TTM）不高于 20 倍", operator: "<=", value: 20, period: null, benchmark: null, status: "supported", reason: null, alternatives: [] },
  { id: "c2", metric: "dividend_yield", label: "股息率（TTM）不低于 3%", operator: ">=", value: 3, period: null, benchmark: null, status: "supported", reason: null, alternatives: [] },
], ranking: [], datasets: [{ key: "valuation", name: "估值快照", status: "supported", as_of: "2026-08-21", coverage: null }], steps: [{ key: "scan", label: "扫描市场数据", status: "pending" }], constraints: [{ field: "pe_ttm", op: "<=", value: 20 }, { field: "dividend_yield", op: ">=", value: 3 }], executable: true, suggested_question: null };
const task = { id: "task-real-1", user_id: "user-1", question: plan.question, template_id: "dividend", scope: { market: "A股" }, constraints: plan.constraints, status: "succeeded", error: null, steps: [{ key: "interpret", label: "解析研究条件", status: "completed" }], created_at: "2026-08-24T10:00:00Z", started_at: "2026-08-24T10:00:00Z", finished_at: "2026-08-24T10:00:01Z" };
const result = { task_id: task.id, question: task.question, template_id: "dividend", summary: "基于本地市场数据筛得 1 个候选。", source: "local_market_store", as_of: "2026-08-21", scope: { market: "A股" }, candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: 0.6, dividend_yield: 5, total_market_value: 2173, reason: "PE 6；股息率 5%", evidence: [{ field: "pe_ttm", value: 6, source: "local_market_store", as_of: "2026-08-21" }] }], risks: ["数据可能存在延迟"], created_at: "2026-08-24T10:00:01Z" };

function responseFor(input: RequestInfo | URL, init?: RequestInit): Response {
  const url = String(input);
  if (url === "/api/public/discovery") return new Response(JSON.stringify(discovery), { status: 200 });
  if (url === "/api/research/tasks?limit=20") return new Response(JSON.stringify([]), { status: 200 });
  if (url === "/api/research/plans" && init?.method === "POST") return new Response(JSON.stringify(plan), { status: 200 });
  if (url === "/api/research/tasks" && init?.method === "POST") return new Response(JSON.stringify(task), { status: 201 });
  if (url === "/api/research/tasks/task-real-1/result") return new Response(JSON.stringify(result), { status: 200 });
  if (url === "/api/research/tasks/task-real-1/thread") return new Response(JSON.stringify({ turns: [{ task, events: [{ id: 1, type: "completed", payload: { message: "研究结果已生成" }, created_at: task.finished_at }], result }] }), { status: 200 });
  return new Response("not found", { status: 404 });
}

// beforeEach 里 vi.stubGlobal 的 fetch 是 vi.fn —— 取它的调用记录
function fetchCalls(): Array<[RequestInfo | URL, RequestInit?]> {
  return (fetch as unknown as { mock: { calls: Array<[RequestInfo | URL, RequestInit?]> } }).mock.calls;
}

describe("LandingPage research planning flow", () => {
  it("presents a user-facing AI analysis chat without technical details", async () => {
    vi.stubGlobal("fetch", vi.fn(responseFor));
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "今天想分析什么？" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "对话历史" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("给 AI 发现发送消息")).toBeInTheDocument();
    expect(screen.getByTestId("ai-analysis-body")).toHaveClass("flex-1", "min-h-0");
    expect(screen.getByTestId("analysis-composer")).toHaveClass("max-w-[760px]");
    // 技术黑话不得出现在分析正文里（站点导航里的「投研 Skills」产品页链接不算）
    expect(within(screen.getByTestId("ai-analysis-body")).queryByText(/AgentLoop|模型|Data Hub 工具|Skills/)).not.toBeInTheDocument();
  });
  beforeEach(() => {
    localStorage.setItem("sigmx_auth_token", "jwt-token");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => responseFor(input, init)));
  });
  afterEach(() => { localStorage.clear(); sessionStorage.clear(); vi.unstubAllGlobals(); });

  it("renders server-provided analysis suggestions", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "低估值高股息" })).toBeInTheDocument();
    expect(screen.queryByText("3,825.76")).not.toBeInTheDocument();
  });

  it("automatically plans and runs research without exposing a plan confirmation", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /低估值高股息/ }));
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByText("平安银行")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "研究计划" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始研究" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "查看完整分析" })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/research/tasks", expect.objectContaining({ method: "POST" })));
  });

  it("restores a saved analysis inside the chat workspace", async () => {
    render(<MemoryRouter initialEntries={["/?conversation=task-real-1"]}><LandingPage /></MemoryRouter>);

    expect(await screen.findByText(result.summary)).toBeInTheDocument();
    expect(screen.getByText(task.question)).toBeInTheDocument();
    expect(screen.getByText("平安银行")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/research/tasks/task-real-1/thread", expect.anything());
    const flow = screen.getByTestId("active-conversation-scroll");
    const stream = screen.getByTestId("conversation-stream");
    const composer = screen.getByTestId("analysis-composer");
    expect(flow).toContainElement(stream);
    expect(flow).not.toContainElement(composer);
    expect(screen.getByTestId("ai-analysis-body")).toContainElement(composer);
    expect(screen.getByTestId("composer-dock")).toHaveClass("absolute", "bottom-0");
  });

  it("clears the composer after sending while keeping the question in the conversation", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    const composer = await screen.findByLabelText("研究问题");
    fireEvent.change(composer, { target: { value: "帮我筛选低估值、高股息的 A 股公司" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(screen.getByText("帮我筛选低估值、高股息的 A 股公司")).toBeInTheDocument();
    expect(composer).toHaveValue("");
  });

  it("does not submit while an IME composition is confirming a candidate word", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    const composer = await screen.findByLabelText("研究问题");
    fireEvent.change(composer, { target: { value: "贵州茅台" } });
    // 中文输入法选字期间的 Enter 是确认候选词，不是发送。
    fireEvent.keyDown(composer, { key: "Enter", isComposing: true });

    expect(composer).toHaveValue("贵州茅台");
    expect(fetchCalls().some(([url]) => String(url) === "/api/research/plans")).toBe(false);
  });

  it("blocks task creation for unavailable conditions and offers a replacement", async () => {
    const unavailable = { ...plan, question: "经营现金流持续改善", executable: false, constraints: [], suggested_question: "寻找低估值公司", conditions: [{ ...plan.conditions[0], id: "cash", metric: "operating_cashflow_trend", label: "经营现金流持续改善", status: "unavailable", reason: "多期数据尚未接入" }] };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => String(input) === "/api/research/plans" ? new Response(JSON.stringify(unavailable), { status: 200 }) : responseFor(input, init));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("研究问题"), { target: { value: unavailable.question } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByRole("heading", { name: "分析没有完成" })).toBeInTheDocument();
    expect(screen.getByText("多期数据尚未接入")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "研究计划" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/research/tasks")).toBe(false);
  });

  it("preserves an executable plan when login is required", async () => {
    localStorage.clear();
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /低估值高股息/ }));
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(sessionStorage.getItem("sigmx.pendingResearchPlan.v1")).toContain("plan-1"));
    expect(fetch).not.toHaveBeenCalledWith("/api/research/tasks", expect.anything());
  });

  it("preserves an executable plan when an existing login has expired", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/research/tasks" && init?.method === "POST") return new Response(JSON.stringify({ detail: "登录已过期" }), { status: 401 });
      return responseFor(input, init);
    }));
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /低估值高股息/ }));
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => expect(sessionStorage.getItem("sigmx.pendingResearchPlan.v1")).toContain("plan-1"));
  });

  it("shows the signed-in user's recent completed research", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => String(input) === "/api/research/tasks?limit=20" ? new Response(JSON.stringify([task]), { status: 200 }) : responseFor(input, init)));
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "对话历史" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: discovery.templates[0].prompt })).toHaveAttribute("href", "/?conversation=task-real-1");
  });

  it("runs deep research locally without LLM planning and posts the pipeline plan", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "个股深度研究" }));
    expect(screen.getByPlaceholderText("输入 6 位股票代码，如 600519")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("研究问题"), { target: { value: "深度研究 600519 的基本面" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    const calls = fetchCalls();
    const post = calls.find(([url, init]) => String(url) === "/api/research/tasks" && init?.method === "POST");
    expect(post).toBeTruthy();
    const body = JSON.parse(String(post?.[1]?.body)) as { plan: { pipeline?: string; code?: string; execution_mode?: string } };
    expect(body.plan.pipeline).toBe("a_stock_deep_research");
    expect(body.plan.code).toBe("600519");
    expect(body.plan.execution_mode).toBe("agent");
    expect(calls.some(([url]) => String(url) === "/api/research/plans")).toBe(false);
  });

  it("rejects deep research without a 6-digit code and creates no task", async () => {
    render(<MemoryRouter><LandingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "个股深度研究" }));
    fireEvent.change(screen.getByLabelText("研究问题"), { target: { value: "贵州茅台" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("深度研究需要 6 位股票代码，例如 600519。")).toBeInTheDocument();
    expect(fetchCalls().some(([url]) => String(url) === "/api/research/tasks")).toBe(false);
  });

  it("activates deep mode with the code prefilled from ?deep=", async () => {
    render(<MemoryRouter initialEntries={["/?deep=600519"]}><LandingPage /></MemoryRouter>);
    const composer = await screen.findByLabelText("研究问题");
    expect(composer).toHaveValue("600519");
    // 深研模式的占位文案（普通模式是“给 AI 发现发送消息”）
    expect(screen.getByPlaceholderText("输入 6 位股票代码，如 600519")).toBeInTheDocument();
  });
});
