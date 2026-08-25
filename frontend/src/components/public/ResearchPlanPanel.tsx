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
  return <section role="dialog" aria-label="研究计划" className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <div className="flex items-start justify-between border-b px-6 py-5">
      <div><div className="text-xs font-semibold text-primary">RESEARCH PLAN</div><h2 className="mt-1 text-xl font-bold">研究计划</h2><p className="mt-2 text-sm text-slate-500">{plan.question}</p></div>
      <button type="button" aria-label="关闭研究计划" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4"/></button>
    </div>
    <div className="grid gap-5 p-6 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div><div className="flex items-center justify-between"><h3 className="font-semibold">系统理解的条件</h3><span className="text-xs text-slate-400">{plan.conditions.length} 项</span></div>
        <div className="mt-3 space-y-3">{plan.conditions.map(item => <article key={item.id} className={`rounded-lg border p-4 ${item.status === "unavailable" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-slate-50"}`}>
          <div className="flex items-start justify-between gap-3"><div><div className="font-medium">{item.label}</div>{(item.period || item.benchmark) && <div className="mt-1 text-xs text-slate-400">{[item.period, item.benchmark].filter(Boolean).join(" · ")}</div>}</div><span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.status === "supported" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}`}>{stateLabel[item.status]}</span></div>
          {item.reason && <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-amber-800"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0"/>{item.reason}</p>}
        </article>)}</div>
      </div>
      <aside className="space-y-4"><div className="rounded-lg border border-slate-200 p-4"><h3 className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary"/>使用数据</h3><div className="mt-3 space-y-2">{plan.datasets.length ? plan.datasets.map(item => <div key={item.key} className="flex items-center gap-2 text-xs text-slate-600"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500"/>{item.name}</div>) : <p className="text-xs leading-5 text-slate-400">当前问题尚未匹配到可执行数据集。</p>}</div></div>
        <div className="rounded-lg border border-slate-200 p-4"><h3 className="text-sm font-semibold">执行步骤</h3><ol className="mt-3 space-y-2">{plan.steps.map((step, index) => <li key={step.key} className="flex gap-2 text-xs text-slate-500"><span className="font-mono text-slate-300">{String(index + 1).padStart(2, "0")}</span>{step.label}</li>)}</ol></div>
      </aside>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-slate-50 px-6 py-4"><p className="text-xs text-slate-500">{plan.executable ? "所有条件均可由当前数据可靠执行。" : "存在暂不可用条件，请采用可执行版本或调整问题。"}</p><div className="flex gap-2">{plan.suggested_question && <button type="button" onClick={() => onUseSuggested(plan.suggested_question!)} className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-semibold"><RefreshCw className="h-4 w-4"/>采用可执行版本</button>}<button type="button" disabled={!plan.executable} onClick={onRun} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">开始研究</button></div></div>
  </section>;
}
