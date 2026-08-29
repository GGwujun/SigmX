import { type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { History, Menu, Pencil, Search, X } from "lucide-react";
import type { ResearchTask } from "@/lib/researchApi";

interface Props { recentTasks: ResearchTask[]; activeTaskId: string | null; onNewAnalysis: () => void; children: ReactNode }
const isToday = (value: string) => new Date(value).toDateString() === new Date().toDateString();

function HistoryList({ tasks, activeTaskId, onSelect }: { tasks: ResearchTask[]; activeTaskId: string | null; onSelect?: () => void }) {
  const groups = useMemo(() => ({ today: tasks.filter(item => isToday(item.created_at)), earlier: tasks.filter(item => !isToday(item.created_at)) }), [tasks]);
  if (!tasks.length) return <div className="mx-3 mt-8 text-center text-sm text-zinc-400"><History className="mx-auto mb-3 h-5 w-5" /><p className="font-medium text-zinc-500">还没有分析记录</p><p className="mt-1 text-xs leading-5">开始一次分析后会显示在这里</p></div>;
  const group = (label: string, items: ResearchTask[]) => items.length ? <section className="mt-5"><h3 className="px-3 text-xs font-medium text-zinc-500">{label}</h3><div className="mt-1 space-y-0.5">{items.map(item => <Link key={item.id} to={`/research/result/${item.id}`} aria-label={item.question} aria-current={item.id === activeTaskId ? "page" : undefined} onClick={onSelect} className={`block truncate rounded-lg px-3 py-2 text-sm transition ${item.id === activeTaskId ? "bg-zinc-200/70 text-zinc-950" : "text-zinc-700 hover:bg-zinc-200/50"}`}>{item.question}</Link>)}</div></section> : null;
  return <>{group("今天", groups.today)}{group("更早", groups.earlier)}</>;
}

function Sidebar({ recentTasks, activeTaskId, onNewAnalysis, onClose }: Omit<Props, "children"> & { onClose?: () => void }) {
  return <div className="flex h-full flex-col bg-[#f7f7f8]">
    <div className="flex items-center justify-between px-4 pb-3 pt-5"><h2 className="text-base font-semibold text-zinc-900">对话历史</h2>{onClose && <button type="button" aria-label="关闭对话历史" onClick={onClose} className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-200"><X className="h-4 w-4" /></button>}</div>
    <div className="px-3"><button type="button" onClick={() => { onNewAnalysis(); onClose?.(); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-200/70"><Pencil className="h-4 w-4" />新建分析</button><label className="mt-2 flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-zinc-400"><Search className="h-4 w-4" /><input placeholder="搜索对话" className="min-w-0 flex-1 bg-transparent text-sm text-zinc-800 outline-none placeholder:text-zinc-400" /></label></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4"><HistoryList tasks={recentTasks} activeTaskId={activeTaskId} onSelect={onClose} /></div>
  </div>;
}

export function AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children }: Props) {
  const [open, setOpen] = useState(false);
  return <div className="bg-white text-zinc-950"><div className="grid h-[calc(100vh-96px)] min-h-[600px] grid-rows-[minmax(0,1fr)] overflow-hidden lg:grid-cols-[240px_minmax(0,1fr)]">
    <aside className="hidden border-r border-zinc-200 lg:block"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} /></aside>
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden"><header className="relative flex h-14 shrink-0 items-center justify-center border-b border-zinc-100 px-4"><button type="button" aria-label="打开对话历史" onClick={() => setOpen(true)} className="absolute left-3 rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 lg:hidden"><Menu className="h-5 w-5" /></button><h1 className="text-sm font-semibold">AI 发现</h1></header>{children}</section>
  </div>{open && <div className="fixed inset-0 z-50 lg:hidden"><button type="button" aria-label="关闭对话历史遮罩" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/20" /><aside className="relative h-full w-[min(84vw,300px)] border-r border-zinc-200 bg-white shadow-xl"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} onClose={() => setOpen(false)} /></aside></div>}</div>;
}
