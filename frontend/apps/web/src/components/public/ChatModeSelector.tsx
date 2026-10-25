/**
 * 聊天列左上角模式选择器（对齐参考图 ChatGPT 顶部左上的选择器位置）：只放真实
 * 存在的两种分析模式——智能分析 / 个股深度研究，切换即改变 composer 的行为与
 * 占位文案，不做无功能的假选项。移动端隐藏（左上是汉堡钮的领域）。
 */
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

interface Props {
  deepMode: boolean;
  onChange: (deep: boolean) => void;
}

const MODES = [
  { deep: false, label: "智能分析", hint: "市场筛选 · 多因子条件 · 支持追问" },
  { deep: true, label: "个股深度研究", hint: "六阶段深研 · 需输入 6 位代码" },
] as const;

export function ChatModeSelector({ deepMode, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const current = MODES.find(mode => mode.deep === deepMode) ?? MODES[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <div data-testid="chat-mode-selector" className="absolute left-3 top-3 z-20 hidden lg:block" ref={rootRef}>
    <button ref={buttonRef} type="button" aria-label="切换分析模式" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(value => !value)} className="inline-flex h-9 items-center gap-1 rounded-full px-3 text-[15px] font-medium text-[#0d0d0d] transition-colors hover:bg-[#f0f0f0]">
      {current.label}<ChevronDown aria-hidden="true" className={`h-4 w-4 text-[#5d5d5d] transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
    </button>
    {open && <div role="menu" aria-label="分析模式" className="absolute left-0 top-11 z-50 w-[280px] rounded-xl border border-[#ececec] bg-white p-1.5 shadow-[0_12px_40px_rgba(0,0,0,.12)]">
      {MODES.map(mode => <button key={mode.label} role="menuitem" type="button" aria-checked={mode.deep === deepMode} onClick={() => {
        setOpen(false);
        if (mode.deep !== deepMode) onChange(mode.deep);
      }} className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-[#f5f5f5]">
        <span className="min-w-0 flex-1">
          <span className={`block text-[13.5px] ${mode.deep === deepMode ? "font-medium text-[#0d0d0d]" : "text-[#0d0d0d]"}`}>{mode.label}</span>
          <span className="mt-0.5 block text-[11.5px] leading-4 text-[#8f8f8f]">{mode.hint}</span>
        </span>
        {mode.deep === deepMode ? <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-[#0d0d0d]" /> : <span aria-hidden="true" className="h-4 w-4 shrink-0" />}
      </button>)}
    </div>}
  </div>;
}
