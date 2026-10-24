import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PublicLayout } from "../PublicLayout";

function renderAt(path: string, label: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route element={<PublicLayout />}>
      <Route path="/intelligence" element={<p>{label}</p>} />
      <Route path="/stock/:code" element={<p>{label}</p>} />
      <Route path="/download" element={<p>{label}</p>} />
    </Route>
  </Routes></MemoryRouter>);
}

afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

describe("PublicLayout 沉浸左栏壳推广", () => {
  it("内容页（情报搜索/个股）并入左栏壳，右侧承载页面内容", () => {
    const first = renderAt("/intelligence", "情报内容");
    // AIAnalysisShell 的左侧栏与右侧工作区
    expect(screen.getByTestId("analysis-workspace")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "对话历史" })).toBeInTheDocument();
    expect(screen.getByText("情报内容")).toBeInTheDocument();

    first.unmount();
    renderAt("/stock/000001", "个股内容");
    expect(screen.getByTestId("analysis-workspace")).toBeInTheDocument();
    expect(screen.getByText("个股内容")).toBeInTheDocument();
  });

  it("下载页等其余路由保持顶栏 + 页脚的常规布局", () => {
    renderAt("/download", "下载内容");
    expect(screen.getByText("下载内容")).toBeInTheDocument();
    expect(screen.queryByTestId("analysis-workspace")).not.toBeInTheDocument();
    // 常规布局带页脚署名
    expect(screen.getByText(/SigmX · 产品分离、平台能力共享/)).toBeInTheDocument();
  });
});
