import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatModeSelector } from "../ChatModeSelector";

describe("ChatModeSelector（左上角分析模式选择器）", () => {
  it("显示当前模式，点开出现菜单（两种真实模式 + 说明 + 选中勾）", () => {
    const onChange = vi.fn();
    render(<ChatModeSelector deepMode={false} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "切换分析模式" })).toHaveTextContent("智能分析");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "切换分析模式" }));
    const menu = screen.getByRole("menu");
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /智能分析/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitem", { name: /个股深度研究/ })).toHaveAttribute("aria-checked", "false");
  });

  it("点另一模式触发 onChange；点当前模式不触发", () => {
    const onChange = vi.fn();
    render(<ChatModeSelector deepMode={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "切换分析模式" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /个股深度研究/ }));
    expect(onChange).toHaveBeenCalledWith(true);
    // 菜单选择后关闭；再次打开点已激活项不重复回调
    fireEvent.click(screen.getByRole("button", { name: "切换分析模式" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /智能分析/ }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("点击菜单外区域关闭菜单", () => {
    render(<ChatModeSelector deepMode onChange={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "切换分析模式" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
