import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResearchProgress } from "../ResearchProgress";

describe("ResearchProgress", () => {
  it("keeps recovery actions available after a failed run", () => {
    const onRetry = vi.fn();
    const onEdit = vi.fn();
    render(<ResearchProgress question="寻找低估值公司" steps={[{ key: "scan", label: "扫描数据", status: "failed" }]} status="error" error="服务暂不可用" onRetry={onRetry} onEdit={onEdit} />);

    expect(screen.getByText("寻找低估值公司")).toBeInTheDocument();
    expect(screen.getByText("服务暂不可用")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    fireEvent.click(screen.getByRole("button", { name: "调整条件" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onEdit).toHaveBeenCalledOnce();
  });
});
