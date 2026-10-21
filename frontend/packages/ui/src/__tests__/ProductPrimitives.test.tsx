import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataTable, EmptyState, ErrorState, MetricStrip, Panel } from "@sigmx/ui";

describe("product UI primitives", () => {
  it("gives a panel an accessible heading and optional action", () => {
    render(<Panel title="关注事件" description="最近 24 小时" action={<button>全部事件</button>}>内容</Panel>);
    expect(screen.getByRole("heading", { name: "关注事件" })).toBeInTheDocument();
    expect(screen.getByText("最近 24 小时")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部事件" })).toBeInTheDocument();
  });

  it("renders metric values with explicit direction rather than color alone", () => {
    render(<MetricStrip items={[{ label: "上涨家数", value: "3,102", change: "+128", direction: "up" }]} />);
    expect(screen.getByText("上涨家数")).toBeInTheDocument();
    expect(screen.getByLabelText("上涨 +128")).toBeInTheDocument();
  });

  it("renders a semantic data table from typed columns", () => {
    render(<DataTable columns={[{ key: "code", header: "代码" }, { key: "name", header: "名称" }]} rows={[{ code: "600519", name: "贵州茅台" }]} rowKey="code" />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "代码" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "贵州茅台" })).toBeInTheDocument();
  });

  it("provides actionable empty and error states", async () => {
    const create = vi.fn();
    const retry = vi.fn();
    const { rerender } = render(<EmptyState title="暂无自选" description="添加标的后在这里跟踪" actionLabel="添加标的" onAction={create} />);
    await userEvent.click(screen.getByRole("button", { name: "添加标的" }));
    expect(create).toHaveBeenCalledOnce();

    rerender(<ErrorState title="加载失败" description="Data Hub 暂不可用" onRetry={retry} />);
    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
