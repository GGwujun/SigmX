import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarkdownDrawer } from "../MarkdownDrawer";
import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

vi.mock("@/lib/conversationFiles", async importOriginal => {
  const actual = await importOriginal<typeof import("@/lib/conversationFiles")>();
  return { ...actual, downloadTextFile: vi.fn() };
});

const doc = (id: string, name: string, content: string): ConversationFile => ({ id, name, kind: "md", typeLabel: "文档", build: () => content });
const first = doc("f1", "分析报告-01-低估值.md", "# 第一篇\n\n低估值结论。");
const second = doc("f2", "分析报告-02-高股息.md", "# 第二篇\n\n高股息结论。");

function renderDrawer(activeId = "f1", overrides: Partial<Parameters<typeof MarkdownDrawer>[0]> = {}) {
  const props = {
    files: [first, second],
    activeId,
    onSelect: vi.fn(),
    onCloseFile: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<MarkdownDrawer {...props} />);
  return props;
}

describe("MarkdownDrawer（多文档 tab 面板）", () => {
  it("渲染每个打开文档一个 tab，激活 tab 标记 aria-selected 并显示其正文", () => {
    renderDrawer("f1");
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(screen.getByText("分析报告-01-低估值.md")).toBeInTheDocument();
    expect(screen.getByText("分析报告-02-高股息.md")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /分析报告-01/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /分析报告-02/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("低估值结论。")).toBeInTheDocument();
    expect(screen.queryByText("高股息结论。")).not.toBeInTheDocument();
  });

  it("点击其他 tab 触发 onSelect 切换", async () => {
    const props = renderDrawer("f1");
    await userEvent.click(screen.getByRole("button", { name: "分析报告-02-高股息.md" }));
    expect(props.onSelect).toHaveBeenCalledWith(second);
  });

  it("tab 上的 × 关闭单个文档（关闭整个面板的按钮不受影响）", async () => {
    const props = renderDrawer("f1");
    await userEvent.click(screen.getByRole("button", { name: "关闭 分析报告-02-高股息.md" }));
    expect(props.onCloseFile).toHaveBeenCalledWith(second);
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("右侧操作：关闭文档面板触发 onClose", async () => {
    const props = renderDrawer("f2");
    await userEvent.click(screen.getByRole("button", { name: "关闭文档面板" }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("下载按钮针对当前激活文档", async () => {
    vi.mocked(downloadTextFile).mockClear();
    renderDrawer("f2");
    await userEvent.click(screen.getByRole("button", { name: "下载当前文档" }));
    expect(downloadTextFile).toHaveBeenCalledWith("分析报告-02-高股息.md", "# 第二篇\n\n高股息结论。", "text/markdown;charset=utf-8");
  });
});
