import { type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { History, Menu, Plus, Search, X } from "lucide-react";
import type { ResearchTask } from "@/lib/researchApi";

interface Props { recentTasks: ResearchTask[]; activeTaskId: string | null; onNewAnalysis: () => void; children: ReactNode }
const isToday = (value: string) => new Date(value).toDateString() === new Date().toDateString();

function HistoryList({ tasks, activeTaskId, onSelect }: { tasks: ResearchTask[]; activeTaskId: string | null; onSelect?: () => void }) {
  const groups = useMemo(() => {
    // Retries of the same question produce many identical rows — keep the newest one.
    const unique = tasks.filter((item, index, all) => all.findIndex(other => other.question === item.question) === index);
    return { today: unique.filter(item => isToday(item.created_at)), earlier: unique.filter(item => !isToday(item.created_at)) };
  }, [tasks]);
  if (!tasks.length) return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><History className="mb-3.5 h-6 w-6 stroke-[1.5] text-slate-600" /><p className="text-[13px] font-medium text-slate-400">还没有分析记录</p><p className="mt-1.5 text-xs leading-5 text-slate-600">开始一次分析后会显示在这里</p></div>;
  const group = (label: string, items: ResearchTask[]) => items.length ? <section className="mt-4"><h3 className="px-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">{label}</h3><div className="mt-1.5 space-y-px">{items.map(item => <Link key={item.id} to={`/?conversation=${item.id}`} aria-label={item.question} aria-current={item.id === activeTaskId ? "page" : undefined} onClick={onSelect} className={`block truncate rounded-lg px-2.5 py-[7px] text-[12px] leading-5 transition-colors ${item.id === activeTaskId ? "bg-teal-400/[0.12] font-medium text-teal-100 ring-1 ring-inset ring-teal-400/25" : "text-slate-400 hover:bg-white/[0.05] hover:text-slate-200"}`}>{item.question}</Link>)}</div></section> : null;
  return <>{group("今天", groups.today)}{group("更早", groups.earlier)}</>;
}

function Sidebar({ recentTasks, activeTaskId, onNewAnalysis, onClose }: Omit<Props, "children"> & { onClose?: () => void }) {
  return <div className="flex h-full flex-col bg-[#101823]">
    <div className="flex items-center justify-between px-4 pb-2.5 pt-4"><h2 className="text-[13px] font-semibold tracking-[0.01em] text-slate-200">对话历史</h2>{onClose && <button type="button" aria-label="关闭对话历史" onClick={onClose} className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"><X className="h-4 w-4" /></button>}</div>
    <div className="px-3"><button type="button" onClick={() => { onNewAnalysis(); onClose?.(); }} className="flex w-full items-center justify-center gap-2 rounded-lg border border-teal-400/25 bg-teal-400/[0.08] px-3 py-2.5 text-[13px] font-semibold text-teal-200 transition-colors hover:border-teal-400/45 hover:bg-teal-400/[0.14]"><Plus className="h-4 w-4 stroke-[2]" />新建分析</button><label className="mt-2.5 flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.03] px-2.5 py-2 transition focus-within:border-teal-400/40 focus-within:bg-white/[0.05]"><Search className="h-3.5 w-3.5 stroke-[1.8] text-slate-500" /><input placeholder="搜索对话" className="min-w-0 flex-1 bg-transparent text-[12px] text-slate-200 outline-none placeholder:text-slate-600" /></label></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-4 pt-1"><HistoryList tasks={recentTasks} activeTaskId={activeTaskId} onSelect={onClose} /></div>
  </div>;
}

export function AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children }: Props) {
  const [open, setOpen] = useState(false);
  // 122px = PublicLayout 顶栏 57（h-14 56 + border 1）+ 页脚 65（border 1 + py-6 48 + 文本 16）。
  // 沉浸态下顶栏/页脚同为深色，画布顶缘只留一道 whisper 分隔即可。
  return <div className="aiw text-slate-100"><div data-testid="analysis-workspace" className="grid h-[calc(100dvh-122px)] min-h-[600px] grid-rows-[minmax(0,1fr)] overflow-hidden border-t border-white/[0.06] lg:grid-cols-[248px_minmax(0,1fr)]">
    <aside className="hidden border-r border-white/[0.08] lg:block"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} /></aside>
    <section className="relative flex min-h-0 min-w-0 flex-col overflow-hidden"><button type="button" aria-label="打开对话历史" onClick={() => setOpen(true)} className="absolute left-3 top-3 z-10 rounded-lg border border-white/10 bg-[#10161f]/90 p-2 text-slate-300 shadow-lg backdrop-blur transition-colors hover:bg-[#161e2a] hover:text-white lg:hidden"><Menu className="h-[19px] w-[19px] stroke-[1.8]" /></button>{children}</section>
  </div>{open && <div className="fixed inset-0 z-50 lg:hidden"><button type="button" aria-label="关闭对话历史遮罩" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/60 backdrop-blur-sm" /><aside className="relative h-full w-[min(84vw,300px)] border-r border-white/10 bg-[#101823] shadow-2xl"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} onClose={() => setOpen(false)} /></aside></div>}</div>;
}
