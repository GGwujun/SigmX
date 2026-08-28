import { type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { History, Menu, MessageSquarePlus, Search, Sparkles, X } from "lucide-react";

import type { ResearchTask } from "@/lib/researchApi";

interface AIAnalysisShellProps {
  recentTasks: ResearchTask[];
  activeTaskId: string | null;
  onNewAnalysis: () => void;
  children: ReactNode;
}

function isToday(value: string): boolean {
  const date = new Date(value);
  const now = new Date();
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate();
}

function HistoryList({
  recentTasks,
  activeTaskId,
  onSelect,
}: {
  recentTasks: ResearchTask[];
  activeTaskId: string | null;
  onSelect?: () => void;
}) {
  const groups = useMemo(() => ({
    today: recentTasks.filter((task) => isToday(task.created_at)),
    earlier: recentTasks.filter((task) => !isToday(task.created_at)),
  }), [recentTasks]);

  if (recentTasks.length === 0) {
    return (
      <div className="mx-2 mt-6 rounded-xl border border-dashed border-slate-200 bg-white/70 px-3 py-6 text-center">
        <History className="mx-auto h-5 w-5 text-slate-300" />
        <p className="mt-2 text-xs font-medium text-slate-500">还没有分析记录</p>
        <p className="mt-1 text-[11px] leading-5 text-slate-400">发起一次分析后，会自动保存在这里。</p>
      </div>
    );
  }

  const renderGroup = (label: string, tasks: ResearchTask[]) => tasks.length > 0 && (
    <section className="mt-5" key={label}>
      <h3 className="px-3 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</h3>
      <div className="mt-2 space-y-1">
        {tasks.map((task) => (
          <Link
            key={task.id}
            to={`/research/result/${task.id}`}
            onClick={onSelect}
            aria-label={task.question}
            aria-current={task.id === activeTaskId ? "page" : undefined}
            className={`block rounded-xl px-3 py-2.5 text-xs leading-5 transition-colors ${
              task.id === activeTaskId
                ? "bg-white font-semibold text-slate-900 shadow-sm ring-1 ring-slate-200"
                : "text-slate-600 hover:bg-white hover:text-slate-900"
            }`}
          >
            <span className="line-clamp-2">{task.question}</span>
            <span className="mt-1 block text-[10px] font-normal text-slate-400">
              {task.status === "succeeded" ? "分析完成" : task.status === "running" ? "分析中" : "研究记录"}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );

  return <>{renderGroup("今天", groups.today)}{renderGroup("更早", groups.earlier)}</>;
}

function HistoryPanel({
  recentTasks,
  activeTaskId,
  onNewAnalysis,
  onClose,
}: Omit<AIAnalysisShellProps, "children"> & { onClose?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-slate-50">
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="text-sm font-bold text-slate-900">对话历史</h2>
        <div className="flex items-center gap-1">
          <button type="button" aria-label="搜索对话历史" className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-slate-700">
            <Search className="h-4 w-4" />
          </button>
          {onClose && (
            <button type="button" aria-label="关闭对话历史" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-slate-700">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      <div className="px-3 py-2">
        <button
          type="button"
          onClick={() => { onNewAnalysis(); onClose?.(); }}
          className="flex w-full items-center gap-2 rounded-xl bg-slate-950 px-3 py-2.5 text-left text-xs font-semibold text-white shadow-sm hover:bg-slate-800"
        >
          <MessageSquarePlus className="h-4 w-4" />
          新建分析
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1 pb-4">
        <HistoryList recentTasks={recentTasks} activeTaskId={activeTaskId} onSelect={onClose} />
      </div>
    </div>
  );
}

export function AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children }: AIAnalysisShellProps) {
  const [historyOpen, setHistoryOpen] = useState(false);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-slate-100 px-3 py-4 text-slate-950 sm:px-5 lg:px-6">
      <div className="mx-auto grid min-h-[calc(100vh-96px)] max-w-[1320px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 lg:block">
          <HistoryPanel recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} />
        </aside>

        <section className="flex min-w-0 flex-col">
          <header className="flex min-h-16 items-center justify-between border-b border-slate-200 px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                aria-label="打开对话历史"
                onClick={() => setHistoryOpen(true)}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
              >
                <Menu className="h-5 w-5" />
              </button>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 text-white shadow-sm">
                <Sparkles className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-bold sm:text-base">SigmX AI 分析</h1>
                <p className="truncate text-[11px] text-slate-500">股票、行业与市场研究助手</p>
              </div>
            </div>
          </header>

          {children}
        </section>
      </div>

      {historyOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" aria-label="关闭对话历史遮罩" onClick={() => setHistoryOpen(false)} className="absolute inset-0 bg-slate-950/30 backdrop-blur-[1px]" />
          <aside className="relative h-full w-[min(84vw,300px)] border-r border-slate-200 bg-white shadow-2xl">
            <HistoryPanel
              recentTasks={recentTasks}
              activeTaskId={activeTaskId}
              onNewAnalysis={onNewAnalysis}
              onClose={() => setHistoryOpen(false)}
            />
          </aside>
        </div>
      )}
    </div>
  );
}
