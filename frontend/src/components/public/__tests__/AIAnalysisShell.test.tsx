import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ResearchTask } from "@/lib/researchApi";
import { AIAnalysisShell } from "../AIAnalysisShell";

const recentTask: ResearchTask = {
  id: "task-1",
  user_id: "user-1",
  question: "低估值高股息机会",
  template_id: "dividend",
  scope: { market: "A股" },
  constraints: [],
  status: "succeeded",
  steps: [],
  error: null,
  created_at: new Date().toISOString(),
  started_at: null,
  finished_at: null,
};

describe("AIAnalysisShell", () => {
  it("shows user-facing analysis history and starts a new analysis", () => {
    const onNewAnalysis = vi.fn();
    render(
      <MemoryRouter>
        <AIAnalysisShell
          recentTasks={[recentTask]}
          activeTaskId={recentTask.id}
          onNewAnalysis={onNewAnalysis}
        >
          <div>当前对话</div>
        </AIAnalysisShell>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "对话历史" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索对话")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI 发现" })).toBeInTheDocument();
    expect(screen.queryByText("股票、行业与市场研究助手")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: recentTask.question })).toHaveAttribute(
      "href",
      `/?conversation=${recentTask.id}`,
    );
    expect(screen.getByText("当前对话")).toBeInTheDocument();
    expect(screen.queryByText(/glm-|provider|api url/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新建分析" }));
    expect(onNewAnalysis).toHaveBeenCalledOnce();
  });

  it("renders an empty history state and exposes the mobile history control", () => {
    render(
      <MemoryRouter>
        <AIAnalysisShell recentTasks={[]} activeTaskId={null} onNewAnalysis={() => undefined}>
          <div>空白分析</div>
        </AIAnalysisShell>
      </MemoryRouter>,
    );

    expect(screen.getByText("还没有分析记录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开对话历史" })).toBeInTheDocument();
  });
});
