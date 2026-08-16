import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataStatus } from "@sigmx/ui";

describe("DataStatus", () => {
  it("shows source, timestamp, freshness and quality together", () => {
    render(<DataStatus source="Tushare" asOf="2026-08-16T08:00:00+08:00" freshness="实时" quality="verified" />);

    expect(screen.getByText("Tushare")).toBeInTheDocument();
    expect(screen.getByText("实时")).toBeInTheDocument();
    expect(screen.getByText("已校验")).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });

  it("makes a degraded data source explicit", () => {
    render(<DataStatus source="备用源" asOf={null} freshness="延迟" quality="degraded" message="主数据源暂不可用" />);

    expect(screen.getByRole("status")).toHaveTextContent("数据降级");
    expect(screen.getByRole("status")).toHaveTextContent("主数据源暂不可用");
  });

  it("offers a retry action when data failed", async () => {
    const retry = vi.fn();
    render(<DataStatus source="Data Hub" asOf={null} freshness="未知" quality="error" message="读取失败" onRetry={retry} />);

    await userEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(retry).toHaveBeenCalledOnce();
  });

  it("accepts compact exchange trade dates", () => {
    render(<DataStatus source="行情库" asOf="20260814" freshness="收盘" quality="verified" />);

    expect(screen.getByText(/2026/)).toBeInTheDocument();
    expect(screen.getByText(/8/)).toBeInTheDocument();
    expect(screen.getByText(/14/)).toBeInTheDocument();
  });
});
