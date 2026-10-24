/**
 * Markdown 预览抽屉（对齐截图：右侧 ~45% 宽覆盖式面板）。顶栏=文件类型块+文件名（∨ 可
 * 换其他 md）+下载+全屏+关闭；正文用 react-markdown 渲染，样式逐级手写对齐文档排版。
 */
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, Download, FileText, Maximize2, Minimize2, X } from "lucide-react";

import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

interface Props {
  file: ConversationFile;
  /** 可切换的其他 md 文件（含当前），仅 1 个时不显示切换下拉。 */
  mdFiles: ConversationFile[];
  onSwitch: (file: ConversationFile) => void;
  onClose: () => void;
}

const components = {
  h1: (props: React.ComponentProps<"h1">) => <h1 className="mb-4 mt-2 text-[24px] font-semibold leading-[1.3] tracking-[-0.015em] text-[#0d0d0d]" {...props} />,
  h2: (props: React.ComponentProps<"h2">) => <h2 className="mb-3 mt-7 text-[18px] font-semibold leading-[1.4] text-[#0d0d0d]" {...props} />,
  h3: (props: React.ComponentProps<"h3">) => <h3 className="mb-2 mt-5 text-[16px] font-semibold text-[#0d0d0d]" {...props} />,
  p: (props: React.ComponentProps<"p">) => <p className="mb-3.5 text-[14.5px] leading-[1.8] text-[#2d2d2d]" {...props} />,
  ul: (props: React.ComponentProps<"ul">) => <ul className="mb-3.5 list-disc space-y-1.5 pl-6 text-[14px] leading-[1.75] text-[#2d2d2d]" {...props} />,
  ol: (props: React.ComponentProps<"ol">) => <ol className="mb-3.5 list-decimal space-y-1.5 pl-6 text-[14px] leading-[1.75] text-[#2d2d2d]" {...props} />,
  blockquote: (props: React.ComponentProps<"blockquote">) => <blockquote className="mb-4 rounded-r-lg border-l-2 border-[#d9d9d9] bg-[#fafafa] py-2 pl-4 pr-3 text-[13px] leading-[1.7] text-[#5d5d5d]" {...props} />,
  table: (props: React.ComponentProps<"table">) => <div className="mb-4 overflow-x-auto"><table className="w-full border-collapse text-[13px]" {...props} /></div>,
  th: (props: React.ComponentProps<"th">) => <th className="border border-[#e5e5e5] bg-[#fafafa] px-2.5 py-2 text-left font-medium text-[#0d0d0d]" {...props} />,
  td: (props: React.ComponentProps<"td">) => <td className="border border-[#e5e5e5] px-2.5 py-2 align-top text-[#2d2d2d]" {...props} />,
  hr: () => <hr className="my-6 border-black/10" />,
  code: (props: React.ComponentProps<"code">) => <code className="rounded bg-[#f5f5f5] px-1 py-0.5 font-mono text-[12.5px] text-[#0d0d0d]" {...props} />,
  pre: (props: React.ComponentProps<"pre">) => <pre className="mb-4 overflow-x-auto rounded-lg bg-[#fafafa] p-3.5 text-[12.5px] leading-[1.6]" {...props} />,
  a: (props: React.ComponentProps<"a">) => <a className="text-[#2563eb] underline underline-offset-2" {...props} />,
  strong: (props: React.ComponentProps<"strong">) => <strong className="font-semibold text-[#0d0d0d]" {...props} />,
};

const iconButton = "grid h-9 w-9 shrink-0 place-items-center rounded-lg text-[#4d4d4d] transition-colors hover:bg-[#f0f0f0] hover:text-[#0d0d0d]";

export function MarkdownDrawer({ file, mdFiles, onSwitch, onClose }: Props) {
  const [full, setFull] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  useEffect(() => {
    if (switcherOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [switcherOpen, onClose]);

  return <div data-testid="markdown-preview" role="dialog" aria-label={`预览 ${file.name}`} className={full
    ? "absolute inset-0 z-50 flex flex-col bg-white shadow-[-12px_0_40px_rgba(0,0,0,.08)]"
    : "absolute inset-y-0 right-0 z-40 flex w-full flex-col border-l border-[#e5e5e5] bg-white shadow-[-12px_0_40px_rgba(0,0,0,.08)] sm:w-[45%]"}>
    <header className="relative flex h-14 shrink-0 items-center gap-2.5 border-b border-[#e5e5e5] px-3 sm:px-4">
      <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#f0f0f0]"><FileText className="h-4 w-4 text-[#2563eb]" /></span>
      <div className="relative min-w-0 flex-1">
        <button type="button" aria-expanded={switcherOpen} aria-haspopup="menu" disabled={mdFiles.length <= 1} onClick={() => setSwitcherOpen(value => !value)} className="flex max-w-full items-center gap-1 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-[#f5f5f5] disabled:hover:bg-transparent">
          <span className="truncate text-[14px] font-medium text-[#0d0d0d]">{file.name}</span>
          {mdFiles.length > 1 && <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 shrink-0 text-[#8f8f8f] transition-transform duration-200 ${switcherOpen ? "rotate-180" : ""}`} />}
        </button>
        {switcherOpen && <div role="menu" className="absolute left-0 top-10 z-10 w-72 max-w-[calc(100vw-48px)] rounded-xl border border-[#e5e5e5] bg-white p-1.5 shadow-[0_12px_40px_rgba(0,0,0,.12)]">
          {mdFiles.map(item => <button key={item.id} role="menuitem" type="button" onClick={() => { onSwitch(item); setSwitcherOpen(false); }} className={`block w-full truncate rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors hover:bg-[#f5f5f5] ${item.id === file.id ? "bg-[#f0f0f0] font-medium text-[#0d0d0d]" : "text-[#0d0d0d]"}`}>{item.name}</button>)}
        </div>}
      </div>
      <button type="button" aria-label="下载文件" onClick={() => downloadTextFile(file.name, file.build(), "text/markdown;charset=utf-8")} className={iconButton}><Download className="h-[18px] w-[18px]" /></button>
      <button type="button" aria-label={full ? "退出全屏" : "全屏查看"} onClick={() => setFull(value => !value)} className={iconButton}>{full ? <Minimize2 className="h-[18px] w-[18px]" /> : <Maximize2 className="h-[18px] w-[18px]" />}</button>
      <button type="button" aria-label="关闭预览" onClick={onClose} className={iconButton}><X className="h-[18px] w-[18px]" /></button>
    </header>
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[640px] px-6 py-8 sm:px-8">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>{file.build()}</Markdown>
      </div>
    </div>
  </div>;
}
