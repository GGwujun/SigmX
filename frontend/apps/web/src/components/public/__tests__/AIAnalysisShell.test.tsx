import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AIAnalysisShell } from "../AIAnalysisShell";

const renderShell = (route = "/") => render(
  <MemoryRouter initialEntries={[route]}>
    <AIAnalysisShell recentTasks={[]} activeTaskId={null} onNewAnalysis={() => undefined}><p>内容</p></AIAnalysisShell>
  </MemoryRouter>,
);

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("AIAnalysisShell 侧栏「查看更多」折叠组", () => {
  it("默认只展示高频研究导航，低频产品页藏进「查看更多」", () => {
    renderShell("/");
    for (const label of ["AI 发现", "情报搜索", "全球事件", "投研 Skills"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    for (const label of ["Desktop", "Data Hub", "套餐"]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "查看更多" })).toBeInTheDocument();
  });

  it("点击「查看更多」展开低频产品页并变成「收起」，状态写入 localStorage", async () => {
    const user = userEvent.setup();
    renderShell("/");
    await user.click(screen.getByRole("button", { name: "查看更多" }));
    for (const label of ["Desktop", "Data Hub", "套餐"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
    expect(localStorage.getItem("sigmx.sidebar.more")).toBe("1");

    await user.click(screen.getByRole("button", { name: "收起" }));
    expect(screen.queryByRole("link", { name: "套餐" })).not.toBeInTheDocument();
    expect(localStorage.getItem("sigmx.sidebar.more")).toBe("0");
  });

  it("正在低频产品页时强制展开且不出现切换行（active 项不可被藏掉）", () => {
    renderShell("/pricing");
    expect(screen.getByRole("link", { name: "套餐" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "查看更多" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收起" })).not.toBeInTheDocument();
  });

  it("localStorage 记住了上次展开：下次进入默认展开", () => {
    localStorage.setItem("sigmx.sidebar.more", "1");
    renderShell("/");
    expect(screen.getByRole("link", { name: "Data Hub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
  });
});
