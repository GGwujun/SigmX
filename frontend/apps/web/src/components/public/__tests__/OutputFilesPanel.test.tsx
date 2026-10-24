import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OutputFilesPanel } from "../OutputFilesPanel";
import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

vi.mock("@/lib/conversationFiles", async importOriginal => {
  const actual = await importOriginal<typeof import("@/lib/conversationFiles")>();
  return { ...actual, downloadTextFile: vi.fn() };
});

const md = (id: string, name: string): ConversationFile => ({ id, name, kind: "md", typeLabel: "文档", build: () => `# ${name}` });
const json = (id: string, name: string): ConversationFile => ({ id, name, kind: "json", typeLabel: "数据", build: () => "{}" });

beforeEach(() => vi.mocked(downloadTextFile).mockClear());

describe("OutputFilesPanel（与聊天同层的输出面板列）", () => {
  it("渲染面板与文件行：名称 + 类型标签", () => {
    render(<OutputFilesPanel files={[md("f1", "分析报告-01-低估值.md"), json("f2", "证据数据-01.json")]} onPreview={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByTestId("output-files-panel")).toBeInTheDocument();
    expect(screen.getByText("输出")).toBeInTheDocument();
    expect(screen.getByText("分析报告-01-低估值.md")).toBeInTheDocument();
    expect(screen.getByText("证据数据-01.json")).toBeInTheDocument();
    expect(screen.getAllByText("文档").length + screen.getAllByText("数据").length).toBe(2);
  });

  it("md 点击走预览回调，json 点击直接下载", async () => {
    const onPreview = vi.fn();
    const files = [md("f1", "分析报告-01-测试.md"), json("f2", "证据数据-01.json")];
    render(<OutputFilesPanel files={files} onPreview={onPreview} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /分析报告-01-测试/ }));
    expect(onPreview).toHaveBeenCalledWith(files[0]);
    expect(downloadTextFile).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /证据数据-01/ }));
    expect(downloadTextFile).toHaveBeenCalledWith("证据数据-01.json", "{}", "application/json;charset=utf-8");
    expect(onPreview).toHaveBeenCalledTimes(1);
  });

  it("超过 5 个文件时折叠并提供「显示更多」，展开后可见全部", async () => {
    const files = Array.from({ length: 7 }, (_, i) => md(`f${i}`, `分析报告-0${i + 1}.md`));
    render(<OutputFilesPanel files={files} onPreview={vi.fn()} onClose={vi.fn()} />);
    expect(screen.queryByText("分析报告-07.md")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /显示更多 2 个/ }));
    expect(screen.getByText("分析报告-07.md")).toBeInTheDocument();
  });

  it("空态给出引导文案", () => {
    render(<OutputFilesPanel files={[]} onPreview={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText(/本次对话还没有可输出的文件/)).toBeInTheDocument();
  });

  it("关闭输出面板按钮回调 onClose", async () => {
    const onClose = vi.fn();
    render(<OutputFilesPanel files={[md("f1", "a.md")]} onPreview={vi.fn()} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "关闭输出面板" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
