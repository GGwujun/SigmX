import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SharedConversationPage } from "../SharedConversationPage";

// 公开投影里的 task 不含 user_id（后端 _public_turn 已剥除）。
const task = { id: "task-1", question: "低估值 高股息筛选", template_id: null, scope: { market: "A股" }, constraints: [], status: "succeeded", steps: [], error: null, created_at: "2026-10-24T10:00:00Z", started_at: "2026-10-24T10:00:00Z", finished_at: "2026-10-24T10:01:00Z" };
const result = { task_id: "task-1", question: task.question, template_id: null, summary: "筛选出 1 个候选：平安银行。", source: "local_market_store", as_of: "2026-10-23", scope: {}, candidates: [], risks: [], created_at: "2026-10-24T10:01:00Z" };
const conversation = { slug: "abc123", question: task.question, created_at: "2026-10-24T10:02:00Z", turns: [{ task, events: [{ id: 1, type: "completed", payload: { message: "研究结果已生成" }, created_at: task.finished_at }], result }] };

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/s/:slug" element={<SharedConversationPage />} /></Routes></MemoryRouter>);
}

afterEach(() => vi.unstubAllGlobals());

describe("SharedConversationPage", () => {
  it("匿名渲染公开对话内容且只读", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(conversation), { status: 200 })));
    renderAt("/s/abc123");

    expect(await screen.findByTestId("shared-conversation")).toBeInTheDocument();
    expect(screen.getByText("低估值 高股息筛选")).toBeInTheDocument();
    expect(screen.getByText(/筛选出 1 个候选/)).toBeInTheDocument();
    // 只读视图：不出现重新生成/重新尝试
    expect(screen.queryByRole("button", { name: "重新生成" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新尝试" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "用 SigmX 创建你自己的分析" })).toHaveAttribute("href", "/");
    expect(screen.getByText(/不构成投资建议/)).toBeInTheDocument();
  });

  it("已撤销（410）与不存在（404）给出对应文案", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "该对话分享已撤销" }), { status: 410 })));
    renderAt("/s/revoked");
    expect(await screen.findByText("该对话分享已撤销")).toBeInTheDocument();

    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "分享链接不存在" }), { status: 404 })));
    renderAt("/s/missing");
    expect(await screen.findByText("未找到该分享")).toBeInTheDocument();
  });

  it("其他错误进入通用错误态", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    renderAt("/s/broken");
    await waitFor(() => expect(screen.getByText("对话暂时不可用")).toBeInTheDocument());
  });
});
