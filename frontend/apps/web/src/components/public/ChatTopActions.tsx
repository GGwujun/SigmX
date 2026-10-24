/**
 * 聊天区右上角操作区（对齐 ChatGPT 截图）：三点下拉 / 分享（真公开链接 + 绿色提示条）/
 * 输出面板开关。菜单里只放真功能——没有 rename/pin/delete 后端，就不放假按钮。
 */
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleSlash, FileDown, FolderOpen, Link2, LoaderCircle, MoreHorizontal, PanelRight, Share, SquarePen, X } from "lucide-react";
import { toast } from "sonner";

import { shareConversation } from "@/lib/researchApi";

interface Props {
  busy: boolean;
  /** 当前对话最后一个 turn 的任务 id：公开分享锚点（分享=公开其祖先链）。 */
  shareTaskId: string | null;
  /** 运行中任务 id（有才显示「取消本次分析」）。 */
  runningTaskId: string | null;
  /** 本对话 URL（?conversation=…），供「复制对话链接」。 */
  conversationUrl: string | null;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onNewAnalysis: () => void;
  onCancel: () => void;
  onExportMarkdown: () => void;
}

const ghostButton = "grid h-9 w-9 place-items-center rounded-full text-[#4d4d4d] transition-colors hover:bg-[#f0f0f0] hover:text-[#0d0d0d]";

export function ChatTopActions({ busy, shareTaskId, runningTaskId, conversationUrl, panelOpen, onTogglePanel, onNewAnalysis, onCancel, onExportMarkdown }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [menuOpen]);

  // 绿色提示条 8 秒自动消失（手动 × 优先）。
  useEffect(() => {
    if (!shareUrl) return;
    const timer = window.setTimeout(() => setShareUrl(null), 8000);
    return () => window.clearTimeout(timer);
  }, [shareUrl]);

  const share = async () => {
    if (!shareTaskId || sharing) return;
    setSharing(true);
    try {
      const item = await shareConversation(shareTaskId);
      const url = `${window.location.origin}/s/${item.slug}`;
      try { await navigator.clipboard.writeText(url); } catch { /* 剪贴板不可用：提示条里展示完整链接 */ }
      setShareUrl(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "分享暂时不可用，请稍后再试");
    } finally {
      setSharing(false);
    }
  };

  const copyConversationLink = async () => {
    if (!conversationUrl) return;
    try {
      await navigator.clipboard.writeText(conversationUrl);
      toast.success("对话链接已复制");
    } catch {
      toast(conversationUrl);
    }
  };

  return <>
    <div data-testid="chat-top-actions" className="absolute right-3 top-3 z-20 flex items-center gap-1" ref={rootRef}>
      <button ref={buttonRef} type="button" aria-label="更多操作" aria-expanded={menuOpen} aria-haspopup="menu" onClick={() => setMenuOpen(value => !value)} className={ghostButton}><MoreHorizontal className="h-[18px] w-[18px] stroke-[1.8]" /></button>
      {menuOpen && <div role="menu" aria-label="对话操作" className="absolute right-0 top-11 z-50 w-[240px] rounded-xl border border-[#ececec] bg-white p-1.5 shadow-[0_12px_40px_rgba(0,0,0,.12)]">
        <MenuItem icon={FolderOpen} label="查看聊天中的文件" onSelect={() => { setMenuOpen(false); onTogglePanel(); }} />
        <MenuItem icon={FileDown} label="导出对话 Markdown" onSelect={() => { setMenuOpen(false); onExportMarkdown(); }} />
        <MenuItem icon={Link2} label="复制对话链接" onSelect={() => { setMenuOpen(false); void copyConversationLink(); }} />
        <div aria-hidden="true" className="my-1 border-t border-[#ececec]" />
        <MenuItem icon={SquarePen} label="新建分析" onSelect={() => { setMenuOpen(false); onNewAnalysis(); }} />
        {busy && runningTaskId && <MenuItem icon={CircleSlash} label="取消本次分析" onSelect={() => { setMenuOpen(false); onCancel(); }} />}
      </div>}
      <button type="button" aria-label="分享对话" onClick={() => void share()} disabled={!shareTaskId || sharing} className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium text-[#4d4d4d] transition-colors hover:bg-[#f0f0f0] hover:text-[#0d0d0d] disabled:cursor-not-allowed disabled:opacity-60">{sharing ? <LoaderCircle className="h-[15px] w-[15px] animate-spin" /> : <Share className="h-[15px] w-[15px] stroke-[1.9]" />}分享</button>
      <button type="button" aria-label="切换输出面板" aria-pressed={panelOpen} onClick={onTogglePanel} className={`${ghostButton} ${panelOpen ? "bg-[#ececec] text-[#0d0d0d] hover:bg-[#e5e5e5]" : ""}`}><PanelRight className="h-[18px] w-[18px] stroke-[1.8]" /></button>
    </div>
    {shareUrl && <div role="status" data-testid="share-toast" className="fixed left-1/2 top-4 z-50 w-[min(560px,92vw)] -translate-x-1/2 rounded-xl bg-[#15803d] px-4 py-3 text-white shadow-[0_12px_40px_rgba(0,0,0,.18)]">
      <div className="flex items-start gap-3">
        <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold leading-6">公开链接已复制</p>
          <p className="mt-0.5 text-[13px] leading-5 text-white/85">任何拥有此链接的人都可以查看此对话。<span className="ml-1 underline underline-offset-2">了解更多</span></p>
          <button type="button" onClick={() => window.open(shareUrl, "_blank", "noopener")} className="mt-2 inline-flex h-7 items-center rounded-full border border-white/60 px-3 text-[12px] font-medium text-white transition-colors hover:bg-white/10">管理链接</button>
        </div>
        <button type="button" aria-label="关闭分享提示" onClick={() => setShareUrl(null)} className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-white/80 transition-colors hover:bg-white/10 hover:text-white"><X className="h-4 w-4" /></button>
      </div>
    </div>}
  </>;
}

function MenuItem({ icon: Icon, label, onSelect }: { icon: typeof FolderOpen; label: string; onSelect: () => void }) {
  return <button role="menuitem" type="button" onClick={onSelect} className="flex h-10 w-full items-center gap-2.5 rounded-lg px-2.5 text-left text-[13px] text-[#0d0d0d] transition-colors hover:bg-[#f5f5f5]"><Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-[#5d5d5d]" />{label}</button>;
}
