/**
 * 「输出」面板列（对齐 ChatGPT canvas 布局）：与聊天区同层并排而非浮层——
 * 桌面端是右侧 340px 常驻列（左缘 1px 分隔线，聊天流收窄），移动端全屏覆盖
 * （顶部带关闭钮）。文件行=图标+名称+右侧类型灰字；点击 md 直接预览、其他
 * 类型直接下载——这正是用户定的规则。
 */
import { useState } from "react";
import { Braces, ChevronDown, FileText, X } from "lucide-react";

import { downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";

interface Props {
  files: ConversationFile[];
  onPreview: (file: ConversationFile) => void;
  onClose: () => void;
}

export function OutputFilesPanel({ files, onPreview, onClose }: Props) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? files : files.slice(0, 5);
  const open = (file: ConversationFile) => {
    if (file.kind === "md") onPreview(file);
    else downloadTextFile(file.name, file.build(), "application/json;charset=utf-8");
  };
  return <aside data-testid="output-files-panel" aria-label="对话输出文件" className="absolute inset-0 z-30 flex flex-col bg-white lg:static lg:z-auto lg:w-[340px] lg:shrink-0 lg:border-l lg:border-[#ececec]">
    {/* 桌面端：灰字小标题贴面板顶部（同参考截图）；移动端：整行头带关闭钮。 */}
    <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#ececec] pl-4 pr-2.5 lg:h-auto lg:border-0 lg:pb-1.5 lg:pt-5">
      <h2 className="text-[15px] font-semibold text-[#0d0d0d] lg:text-[12.5px] lg:font-medium lg:text-[#8f8f8f]">输出</h2>
      <button type="button" aria-label="关闭输出面板" onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full text-[#4d4d4d] transition-colors hover:bg-[#f0f0f0] lg:hidden"><X aria-hidden="true" className="h-[18px] w-[18px]" /></button>
    </div>
    {files.length === 0
      ? <p className="px-4 pt-1 text-[12.5px] leading-5 text-[#8f8f8f] lg:px-3.5">本次对话还没有可输出的文件，完成后会在这里列出报告与数据。</p>
      : <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 lg:px-2.5">
        {visible.map(file => <button key={file.id} type="button" onClick={() => open(file)} className="flex h-10 w-full items-center gap-2.5 rounded-lg px-2.5 text-left transition-colors hover:bg-[#f5f5f5]">
          {file.kind === "md" ? <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-[#2563eb]" /> : <Braces aria-hidden="true" className="h-4 w-4 shrink-0 text-[#5d5d5d]" />}
          <span className="min-w-0 flex-1 truncate text-[13px] text-[#0d0d0d]">{file.name}</span>
          <span className="shrink-0 text-[12px] text-[#8f8f8f]">{file.typeLabel}</span>
        </button>)}
        {files.length > 5 && <button type="button" onClick={() => setExpanded(value => !value)} className="flex h-9 w-full items-center justify-center gap-1 rounded-lg text-[12px] font-medium text-[#5d5d5d] transition-colors hover:bg-[#f5f5f5]"><ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />{expanded ? "收起" : `显示更多 ${files.length - 5} 个`}</button>}
      </div>}
  </aside>;
}
