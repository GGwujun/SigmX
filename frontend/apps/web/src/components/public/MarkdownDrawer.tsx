/**
 * Markdown 文档面板（对齐参考图的多文档 tab 交互）：可同时打开多个文档，
 * 顶栏每个文档一个 tab（图标+文件名+单个关闭 ×，点 tab 切换、点 × 关单个，
 * 全关即收面板）；tab 行右侧是当前文档的下载/全屏/关闭面板操作。桌面与聊天
 * 区同层并排（~45% 宽，把聊天往左挤压），移动端全屏覆盖。正文用 react-markdown
 * 渲染，样式逐级手写对齐文档排版。
 */
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText, Maximize2, Minimize2, X } from "lucide-react";

import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

interface Props {
  /** 当前打开的文档列表（≥1，面板才渲染）。 */
  files: ConversationFile[];
  /** 激活（正在查看）的文档 id。 */
  activeId: string;
  onSelect: (file: ConversationFile) => void;
  onCloseFile: (file: ConversationFile) => void;
  onClose: () => void;
}

const components = {
  h1: (props: React.ComponentProps<"h1">) => <h1 className="mb-3.5 mt-1.5 text-[22px] font-semibold leading-[1.35] tracking-[-0.015em] text-[#0d0d0d]" {...props} />,
  h2: (props: React.ComponentProps<"h2">) => <h2 className="mb-2.5 mt-6 text-[17px] font-semibold leading-[1.4] text-[#0d0d0d]" {...props} />,
  h3: (props: React.ComponentProps<"h3">) => <h3 className="mb-2 mt-4 text-[15px] font-semibold text-[#0d0d0d]" {...props} />,
  p: (props: React.ComponentProps<"p">) => <p className="mb-3 text-[15px] leading-[1.7] text-[#2d2d2d]" {...props} />,
  ul: (props: React.ComponentProps<"ul">) => <ul className="mb-3 list-disc space-y-1.5 pl-6 text-[15px] leading-[1.7] text-[#2d2d2d]" {...props} />,
  ol: (props: React.ComponentProps<"ol">) => <ol className="mb-3 list-decimal space-y-1.5 pl-6 text-[15px] leading-[1.7] text-[#2d2d2d]" {...props} />,
  blockquote: (props: React.ComponentProps<"blockquote">) => <blockquote className="mb-3.5 rounded-r-lg border-l-2 border-[#d9d9d9] bg-[#fafafa] py-2 pl-4 pr-3 text-[13px] leading-[1.7] text-[#5d5d5d]" {...props} />,
  // ChatGPT canvas 式表格：只保留横线（表头下加重、行间浅灰），无竖线网格。
  table: (props: React.ComponentProps<"table">) => <div className="mb-4 overflow-x-auto"><table className="w-full border-collapse text-[13.5px]" {...props} /></div>,
  thead: (props: React.ComponentProps<"thead">) => <thead className="border-b border-[#d9d9e3]" {...props} />,
  th: (props: React.ComponentProps<"th">) => <th className="border-0 px-3 py-2.5 text-left text-[12.5px] font-semibold text-[#5d5d5d] first:pl-0 last:pr-0" {...props} />,
  td: (props: React.ComponentProps<"td">) => <td className="border-b border-[#ececec] px-3 py-2.5 align-top text-[#2d2d2d] first:pl-0 last:pr-0" {...props} />,
  hr: () => <hr className="my-6 border-black/10" />,
  code: (props: React.ComponentProps<"code">) => <code className="rounded bg-[#f5f5f5] px-1 py-0.5 font-mono text-[13px] text-[#0d0d0d]" {...props} />,
  pre: (props: React.ComponentProps<"pre">) => <pre className="mb-3.5 overflow-x-auto rounded-lg bg-[#fafafa] p-3.5 text-[13px] leading-[1.6]" {...props} />,
  a: (props: React.ComponentProps<"a">) => <a className="text-[#2563eb] underline underline-offset-2" {...props} />,
  strong: (props: React.ComponentProps<"strong">) => <strong className="font-semibold text-[#0d0d0d]" {...props} />,
};

const iconButton = "grid h-9 w-9 shrink-0 place-items-center rounded-lg text-[#4d4d4d] transition-colors hover:bg-black/[0.06] hover:text-[#0d0d0d]";

export function MarkdownDrawer({ files, activeId, onSelect, onCloseFile, onClose }: Props) {
  const [full, setFull] = useState(false);
  const active = files.find(file => file.id === activeId) ?? files[0];

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);

  if (!active) return null;
  return <div data-testid="markdown-preview" role="dialog" aria-label={`预览 ${active.name}`} className={full
    ? "absolute inset-0 z-50 flex w-full flex-col bg-white"
    : "absolute inset-0 z-40 flex w-full flex-col bg-white lg:static lg:z-auto lg:w-[45%] lg:shrink-0 lg:border-l lg:border-[#e5e5e5]"}>
    {/* tab 栏：浅灰底条 + 文件夹式 tab——活动 tab 白底带上圆角边框、-mb-px 盖住
        底部分割线，与下方白色正文连成一体；非活动 tab 透明灰字，悬停微底色。 */}
    <header className="flex h-12 shrink-0 items-stretch border-b border-[#e5e5e5] bg-[#f7f7f8] pl-1.5 pr-2 pt-1.5 sm:pl-2.5">
      <div role="tablist" aria-label="打开的文档" className="aiw flex min-w-0 flex-1 items-end gap-0.5 overflow-x-auto">
        {files.map(file => {
          const isActive = file.id === active.id;
          return <div key={file.id} role="tab" aria-selected={isActive} className={`flex max-w-[240px] shrink-0 items-center ${isActive
            ? "-mb-px h-[37px] rounded-t-[10px] border border-b-0 border-[#e5e5e5] bg-white pr-1 pl-2"
            : "h-8 rounded-t-[10px] pl-2 pr-1.5 transition-colors hover:bg-black/[0.045]"}`}>
            <button type="button" onClick={() => onSelect(file)} className="flex min-w-0 items-center gap-1.5 py-1 pl-1 pr-1 text-left">
              <FileText aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#2563eb]" />
              <span className={`truncate text-[13px] ${isActive ? "font-medium text-[#0d0d0d]" : "text-[#5d5d5d]"}`}>{file.name}</span>
            </button>
            <button type="button" aria-label={`关闭 ${file.name}`} onClick={() => onCloseFile(file)} className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-[#8f8f8f] transition-colors hover:bg-black/[0.06] hover:text-[#0d0d0d]"><X className="h-3.5 w-3.5" /></button>
          </div>;
        })}
      </div>
      <div className="flex shrink-0 items-center gap-0.5 self-center">
        <button type="button" aria-label="下载当前文档" onClick={() => downloadTextFile(active.name, active.build(), "text/markdown;charset=utf-8")} className={iconButton}><Download className="h-[18px] w-[18px]" /></button>
        <button type="button" aria-label={full ? "退出全屏" : "全屏查看"} onClick={() => setFull(value => !value)} className={iconButton}>{full ? <Minimize2 className="h-[18px] w-[18px]" /> : <Maximize2 className="h-[18px] w-[18px]" />}</button>
        <button type="button" aria-label="关闭文档面板" onClick={onClose} className={iconButton}><X className="h-[18px] w-[18px]" /></button>
      </div>
    </header>
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[640px] px-6 py-7 sm:px-8">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>{active.build()}</Markdown>
      </div>
    </div>
  </div>;
}
