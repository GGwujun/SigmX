import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { ChatTopActions } from "../ChatTopActions";
import { shareConversation } from "@/lib/researchApi";

vi.mock("@/lib/researchApi", () => ({ shareConversation: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

type Props = Parameters<typeof ChatTopActions>[0];
const props = (overrides: Partial<Props> = {}): Props => ({
  busy: false,
  shareTaskId: "task-1",
  runningTaskId: null,
  conversationUrl: "https://sigmx.test/?conversation=task-1",
  panelOpen: false,
  onTogglePanel: vi.fn(),
  onNewAnalysis: vi.fn(),
  onCancel: vi.fn(),
  onExportMarkdown: vi.fn(),
  ...overrides,
});

const writeText = vi.fn(async () => undefined);

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  vi.mocked(shareConversation).mockReset();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  delete (navigator as { clipboard?: unknown }).clipboard;
  vi.restoreAllMocks();
});

describe("ChatTopActions", () => {
  it("三点菜单列出真实操作，选择后关闭并回调", () => {
    const p = props();
    render(<ChatTopActions {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    const menu = screen.getByRole("menu", { name: "对话操作" });
    for (const label of ["查看聊天中的文件", "导出对话 Markdown", "复制对话链接", "新建分析"]) {
      expect(within(menu).getByRole("menuitem", { name: label })).toBeInTheDocument();
    }
    // 没有运行中的任务就没有「取消本次分析」
    expect(within(menu).queryByRole("menuitem", { name: "取消本次分析" })).not.toBeInTheDocument();

    fireEvent.click(within(menu).getByRole("menuitem", { name: "查看聊天中的文件" }));
    expect(p.onTogglePanel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("运行中任务提供「取消本次分析」入口", () => {
    const p = props({ busy: true, runningTaskId: "task-1" });
    render(<ChatTopActions {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "取消本次分析" }));
    expect(p.onCancel).toHaveBeenCalledTimes(1);
  });

  it("分享成功复制公开链接并显示绿色提示条", async () => {
    vi.mocked(shareConversation).mockResolvedValue({ id: "share-1", task_id: "task-1", slug: "abc123", created_at: "2026-10-24T10:00:00Z", revoked_at: null });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<ChatTopActions {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "分享对话" }));
    await waitFor(() => expect(screen.getByTestId("share-toast")).toBeInTheDocument());

    expect(shareConversation).toHaveBeenCalledWith("task-1");
    expect(screen.getByText("公开链接已复制")).toBeInTheDocument();
    expect(screen.getByText(/任何拥有此链接的人都可以查看此对话/)).toBeInTheDocument();
    const url = `${window.location.origin}/s/abc123`;
    expect(writeText).toHaveBeenCalledWith(url);

    fireEvent.click(screen.getByRole("button", { name: "管理链接" }));
    expect(open).toHaveBeenCalledWith(url, "_blank", "noopener");

    fireEvent.click(screen.getByRole("button", { name: "关闭分享提示" }));
    expect(screen.queryByTestId("share-toast")).not.toBeInTheDocument();
  });

  it("分享失败走错误提示，不出现成功条", async () => {
    vi.mocked(shareConversation).mockRejectedValue(new Error("内容触发合规限制，无法公开分享"));
    render(<ChatTopActions {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "分享对话" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("内容触发合规限制，无法公开分享"));
    expect(screen.queryByTestId("share-toast")).not.toBeInTheDocument();
  });

  it("提示条 8 秒后自动消失", async () => {
    vi.useFakeTimers();
    vi.mocked(shareConversation).mockResolvedValue({ id: "share-1", task_id: "task-1", slug: "abc123", created_at: "2026-10-24T10:00:00Z", revoked_at: null });
    render(<ChatTopActions {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "分享对话" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(screen.getByTestId("share-toast")).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(8000); });
    expect(screen.queryByTestId("share-toast")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("面板按钮回调切换并反映激活态；无对话时分享禁用", () => {
    const p = props({ panelOpen: true });
    const first = render(<ChatTopActions {...p} />);
    const panel = screen.getByRole("button", { name: "切换输出面板" });
    expect(panel).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(panel);
    expect(p.onTogglePanel).toHaveBeenCalledTimes(1);

    first.unmount();
    render(<ChatTopActions {...props({ shareTaskId: null })} />);
    expect(screen.getByRole("button", { name: "分享对话" })).toBeDisabled();
  });
});
