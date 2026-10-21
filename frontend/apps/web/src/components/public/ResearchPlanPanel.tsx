import { AlertTriangle, CheckCircle2, Database, RefreshCw, X } from "lucide-react";
import type { ResearchPlan } from "@/lib/researchApi";

interface Props {
  plan: ResearchPlan;
  onUseSuggested: (question: string) => void;
  onRun: () => void;
  onClose: () => void;
}

const stateLabel = { supported: "可执行", degraded: "可替代", unavailable: "暂不可用" } as const;

export function ResearchPlanPanel({ plan, onUseSuggested, onRun, onClose }: Props) {
  return <section role="dialog" aria-label="研究计划" className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
    <div className="flex items-start justify-between border-b border-zinc-100 px-5 py-4">
      <div><h2 className="text-[16px] font-semibold tracking-[-0.02em] text-zinc-950">研究计划</h2><p className="mt-1.5 text-[13px] leading-5 text-zinc-500">{plan.question}</p></div>
      <button type="button" aria-label="关闭研究计划" onClick={onClose} className="rounded-lg p-2 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"><X className="h-4 w-4"/></button>
    </div>
    <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_230px]">
      <div><div className="flex items-center justify-between"><h3 className="text-[13px] font-semibold text-zinc-900">系统理解的条件</h3><span className="text-[11px] text-zinc-400">{plan.conditions.length} 项</span></div>
        <div className="mt-3 space-y-2">{plan.conditions.map(item => <article key={item.id} className={`rounded-xl border px-3.5 py-3 ${item.status === "unavailable" ? "border-amber-200 bg-amber-50/60" : "border-zinc-100 bg-zinc-50/80"}`}>
          <div className="flex items-start justify-between gap-3"><div><div className="text-[13px] font-medium text-zinc-900">{item.label}</div>{(item.period || item.benchmark) && <div className="mt-1 text-[11px] text-zinc-400">{[item.period, item.benchmark].filter(Boolean).join(" · ")}</div>}</div><span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-medium ${item.status === "supported" ? "bg-zinc-200/80 text-zinc-700" : "bg-amber-100 text-amber-800"}`}>{stateLabel[item.status]}</span></div>
          {item.reason && <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-amber-800"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0"/>{item.reason}</p>}
        </article>)}</div>
      </div>
      <aside className="space-y-3"><div className="rounded-xl border border-zinc-100 p-3.5"><h3 className="flex items-center gap-2 text-[13px] font-semibold text-zinc-900"><Database className="h-3.5 w-3.5 text-zinc-500"/>使用数据</h3><div className="mt-2.5 space-y-2">{plan.datasets.length ? plan.datasets.map(item => <div key={item.key} className="flex items-center gap-2 text-[11px] text-zinc-600"><CheckCircle2 className="h-3.5 w-3.5 text-zinc-500"/>{item.name}</div>) : <p className="text-[11px] leading-5 text-zinc-400">当前问题尚未匹配到可执行数据集。</p>}</div></div>
        <div className="rounded-xl border border-zinc-100 p-3.5"><h3 className="text-[13px] font-semibold text-zinc-900">执行步骤</h3><ol className="mt-2.5 space-y-2">{plan.steps.map((step, index) => <li key={step.key} className="flex gap-2 text-[11px] leading-4 text-zinc-500"><span className="font-mono text-zinc-300">{String(index + 1).padStart(2, "0")}</span>{step.label}</li>)}</ol></div>
      </aside>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 bg-zinc-50/60 px-5 py-3.5"><p className="text-[11px] text-zinc-500">{plan.executable ? "所有条件均可由当前数据可靠执行。" : "存在暂不可用条件，请采用可执行版本或调整问题。"}</p><div className="flex gap-2">{plan.suggested_question && <button type="button" onClick={() => onUseSuggested(plan.suggested_question!)} className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3.5 py-2 text-[13px] font-medium text-zinc-800"><RefreshCw className="h-3.5 w-3.5"/>采用可执行版本</button>}<button type="button" disabled={!plan.executable} onClick={onRun} className="rounded-lg bg-zinc-950 px-3.5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40">开始研究</button></div></div>
  </section>;
}
