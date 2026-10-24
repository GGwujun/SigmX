/**
 * 「输出」浮层面板（对齐 ChatGPT 交互）：右上角面板钮打开的是悬浮在聊天区
 * 右上角的文件卡片——不挤压聊天；点击具体 md 文档才打开右侧文档面板（那一步
 * 才挤压聊天区）。文件行=图标+名称+右侧类型灰字；md 点击预览、其他类型直接下载。
 */
import { useState } from "react";
import { Braces, ChevronDown, FileText } from "lucide-react";

import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

interface Props {
  files: ConversationFile[];
  onPreview: (file: ConversationFile) => void;
}

export function OutputFilesPanel({ files, onPreview }: Props) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? files : files.slice(0, 5);
  const open = (file: ConversationFile) => {
    if (file.kind === "md") onPreview(file);
    else downloadTextFile(file.name, file.build(), "application/json;charset=utf-8");
  };
  return <div data-testid="output-files-panel" className="absolute right-3 top-14 z-30 w-[320px] max-w-[calc(100vw-24px)] rounded-2xl border border-[#e5e5e5] bg-white p-1.5 shadow-[0_12px_40px_rgba(0,0,0,.12)]">
    <h2 className="px-2.5 pb-1 pt-2 text-[12.5px] font-medium text-[#8f8f8f]">输出</h2>
    {files.length === 0
      ? <p className="px-2.5 pb-3 pt-0.5 text-[12.5px] leading-5 text-[#8f8f8f]">本次对话还没有可输出的文件，完成后会在这里列出报告与数据。</p>
      : <div className="pb-1">
        {visible.map(file => <button key={file.id} type="button" onClick={() => open(file)} className="flex h-10 w-full items-center gap-2.5 rounded-lg px-2.5 text-left transition-colors hover:bg-[#f5f5f5]">
          {file.kind === "md" ? <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-[#2563eb]" /> : <Braces aria-hidden="true" className="h-4 w-4 shrink-0 text-[#5d5d5d]" />}
          <span className="min-w-0 flex-1 truncate text-[13px] text-[#0d0d0d]">{file.name}</span>
          <span className="shrink-0 text-[12px] text-[#8f8f8f]">{file.typeLabel}</span>
        </button>)}
        {files.length > 5 && <button type="button" onClick={() => setExpanded(value => !value)} className="flex h-9 w-full items-center justify-center gap-1 rounded-lg text-[12px] font-medium text-[#5d5d5d] transition-colors hover:bg-[#f5f5f5]"><ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />{expanded ? "收起" : `显示更多 ${files.length - 5} 个`}</button>}
      </div>}
  </div>;
}
