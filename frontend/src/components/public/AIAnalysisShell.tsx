import { type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { History, Menu, Pencil, Search, X } from "lucide-react";
import type { ResearchTask } from "@/lib/researchApi";

interface Props { recentTasks: ResearchTask[]; activeTaskId: string | null; onNewAnalysis: () => void; children: ReactNode }
const isToday = (value: string) => new Date(value).toDateString() === new Date().toDateString();

function HistoryList({ tasks, activeTaskId, onSelect }: { tasks: ResearchTask[]; activeTaskId: string | null; onSelect?: () => void }) {
  const groups = useMemo(() => {
    // Retries of the same question produce many identical rows — keep the newest one.
    const unique = tasks.filter((item, index, all) => all.findIndex(other => other.question === item.question) === index);
    return { today: unique.filter(item => isToday(item.created_at)), earlier: unique.filter(item => !isToday(item.created_at)) };
  }, [tasks]);
  if (!tasks.length) return <div className="mx-4 mt-12 text-center text-sm text-zinc-400"><History className="mx-auto mb-3 h-[18px] w-[18px] stroke-[1.7]" /><p className="font-medium text-zinc-600">还没有分析记录</p><p className="mt-1.5 text-xs leading-5 text-zinc-400">开始一次分析后会显示在这里</p></div>;
  const group = (label: string, items: ResearchTask[]) => items.length ? <section className="mt-4"><h3 className="px-2.5 text-[11px] font-medium text-zinc-500">{label}</h3><div className="mt-1 space-y-px">{items.map(item => <Link key={item.id} to={`/?conversation=${item.id}`} aria-label={item.question} aria-current={item.id === activeTaskId ? "page" : undefined} onClick={onSelect} className={`block truncate rounded-lg px-2.5 py-[7px] text-[12px] leading-5 transition-colors ${item.id === activeTaskId ? "bg-zinc-200/75 font-medium text-zinc-950" : "text-zinc-700 hover:bg-zinc-200/55 hover:text-zinc-950"}`}>{item.question}</Link>)}</div></section> : null;
  return <>{group("今天", groups.today)}{group("更早", groups.earlier)}</>;
}

function Sidebar({ recentTasks, activeTaskId, onNewAnalysis, onClose }: Omit<Props, "children"> & { onClose?: () => void }) {
  return <div className="flex h-full flex-col bg-[#f7f7f8]">
    <div className="flex items-center justify-between px-3.5 pb-2 pt-3.5"><h2 className="text-[14px] font-semibold tracking-[-0.01em] text-zinc-950">对话历史</h2>{onClose && <button type="button" aria-label="关闭对话历史" onClick={onClose} className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800"><X className="h-4 w-4" /></button>}</div>
    <div className="px-2.5"><button type="button" onClick={() => { onNewAnalysis(); onClose?.(); }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-[7px] text-[12px] font-medium text-zinc-800 transition-colors hover:bg-zinc-200/70"><Pencil className="h-4 w-4 stroke-[1.8]" />新建分析</button><label className="mt-2 flex items-center gap-2 rounded-lg border border-zinc-200/90 bg-white/80 px-2.5 py-2 text-zinc-400 transition focus-within:border-zinc-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-zinc-200/60"><Search className="h-3.5 w-3.5 stroke-[1.8]" /><input placeholder="搜索对话" className="min-w-0 flex-1 bg-transparent text-[12px] text-zinc-800 outline-none placeholder:text-zinc-400" /></label></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4"><HistoryList tasks={recentTasks} activeTaskId={activeTaskId} onSelect={onClose} /></div>
  </div>;
}

export function AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children }: Props) {
  const [open, setOpen] = useState(false);
  return <div className="bg-white text-zinc-950"><div data-testid="analysis-workspace" className="grid h-[calc(100vh-96px)] min-h-[600px] grid-rows-[minmax(0,1fr)] overflow-hidden lg:grid-cols-[232px_minmax(0,1fr)]">
    <aside className="hidden border-r border-zinc-200/80 lg:block"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} /></aside>
    <section className="relative flex min-h-0 min-w-0 flex-col overflow-hidden"><button type="button" aria-label="打开对话历史" onClick={() => setOpen(true)} className="absolute left-3 top-3 z-10 rounded-lg border border-zinc-200 bg-white/90 p-2 text-zinc-500 shadow-sm backdrop-blur transition-colors hover:bg-zinc-100 hover:text-zinc-800 lg:hidden"><Menu className="h-[19px] w-[19px] stroke-[1.8]" /></button>{children}</section>
  </div>{open && <div className="fixed inset-0 z-50 lg:hidden"><button type="button" aria-label="关闭对话历史遮罩" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/20" /><aside className="relative h-full w-[min(84vw,300px)] border-r border-zinc-200 bg-white shadow-xl"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} onClose={() => setOpen(false)} /></aside></div>}</div>;
}
