import { AlertCircle, CheckCircle2, LoaderCircle } from "lucide-react";
import type { ResearchStep } from "@/lib/researchApi";

interface Props { question: string; steps: ResearchStep[]; status: "running" | "error"; error?: string; onRetry: () => void; onEdit: () => void }

export function ResearchProgress({ question, steps, status, error, onRetry, onEdit }: Props) {
  return <section aria-label="研究执行状态" className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    <div className="flex items-start gap-3">{status === "running" ? <LoaderCircle className="mt-0.5 h-5 w-5 animate-spin text-primary"/> : <AlertCircle className="mt-0.5 h-5 w-5 text-red-500"/>}<div><h2 className="font-bold">{status === "running" ? "正在执行研究" : "研究未完成"}</h2><p className="mt-1 text-sm text-slate-500">{question}</p></div></div>
    <div className="mt-6 grid gap-2">{steps.map(step => <div key={step.key} className="flex items-center gap-3 rounded-lg bg-slate-50 px-4 py-3 text-sm"><span>{step.status === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500"/> : step.status === "running" ? <LoaderCircle className="h-4 w-4 animate-spin text-primary"/> : <span className="block h-4 w-4 rounded-full border border-slate-300"/>}</span><span>{step.label}</span></div>)}</div>
    {status === "error" && <div className="mt-5"><div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error || "研究服务暂时不可用"}</div><div className="mt-4 flex gap-2"><button type="button" onClick={onRetry} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">重试</button><button type="button" onClick={onEdit} className="rounded-lg border px-4 py-2 text-sm font-semibold">调整条件</button></div></div>}
  </section>;
}
