import { AlertCircle, ArrowRight, Check, ChevronDown, Copy, LoaderCircle, RefreshCw, RotateCcw, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ResearchPlanPanel } from "./ResearchPlanPanel";
import type { ResearchPlan, ResearchResult, ResearchTask } from "@/lib/researchApi";

export type AIAnalysisRunState = "idle" | "planning" | "plan" | "running" | "done" | "error";
export interface ResearchEvent { id: number; type: string; payload: Record<string, unknown> }
interface Props { phase: AIAnalysisRunState; question: string; plan: ResearchPlan | null; task: ResearchTask | null; events: ResearchEvent[]; result: ResearchResult | null; loadError: string; runError: string; onRun: () => void; onRetry: () => void; onUseSuggested: (question: string) => void; onResetPlan: () => void }

export function AIAnalysisTimeline(props: Props) {
  const { phase, question, plan, task, result, loadError, runError } = props;
  if (phase === "idle") return <div className="mx-auto flex min-h-[480px] max-w-2xl flex-col items-center justify-center px-6 pb-24 text-center"><span className="grid h-11 w-11 place-items-center rounded-full bg-zinc-900 text-white"><Sparkles className="h-5 w-5" /></span><h2 className="mt-5 text-2xl font-semibold tracking-tight">今天想分析什么？</h2><p className="mt-3 text-sm leading-6 text-zinc-500">描述你关注的股票、行业或筛选条件，我会先整理计划，再逐步完成分析。</p>{loadError && <p className="mt-5 text-sm text-amber-700">部分市场信息暂时不可用，但仍可继续创建分析。</p>}</div>;

  const steps = task?.steps ?? plan?.steps ?? [];
  return <div className="mx-auto w-full max-w-[820px] space-y-8 px-5 py-8 pb-32 sm:px-8">
    {question && <div className="flex justify-end"><div className="max-w-[78%] rounded-3xl bg-[#f4f4f4] px-5 py-3 text-[15px] leading-6 text-zinc-900">{question}</div></div>}
    {phase === "planning" && <Assistant><p className="flex items-center gap-2 text-[15px]"><LoaderCircle className="h-4 w-4 animate-spin" />正在理解你的研究问题</p><p className="mt-2 text-sm text-zinc-500">马上为你整理可确认的分析步骤</p></Assistant>}
    {phase === "plan" && plan && <Assistant><p className="mb-1 text-[15px] leading-7">我整理了一份研究计划</p><p className="mb-4 text-sm text-zinc-500">请确认后开始分析。</p><div className="overflow-hidden rounded-xl border border-zinc-200 [&_[role=dialog]]:border-0 [&_[role=dialog]]:shadow-none"><ResearchPlanPanel plan={plan} onUseSuggested={props.onUseSuggested} onRun={props.onRun} onClose={props.onResetPlan} /></div></Assistant>}
    {phase === "running" && <Assistant><p className="flex items-center gap-2 text-[15px]"><LoaderCircle className="h-4 w-4 animate-spin" />正在分析市场数据</p><div className="mt-5 divide-y divide-zinc-100 border-y border-zinc-100">{steps.map((step, index) => <div key={step.key} className="flex items-center gap-3 py-3 text-sm text-zinc-600"><span className="grid h-5 w-5 place-items-center rounded-full bg-zinc-100 text-[11px]">{step.status === "completed" || step.status === "succeeded" ? <Check className="h-3 w-3" /> : index + 1}</span>{step.label}</div>)}</div></Assistant>}
    {phase === "done" && result && <Assistant><Result result={result} stepCount={steps.length} /></Assistant>}
    {phase === "error" && <Assistant><div className="flex items-start gap-3 text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="font-semibold">分析没有完成</h2><p className="mt-2 text-sm leading-6 text-zinc-600">{runError || "暂时无法完成本次分析，请稍后再试。"}</p><div className="mt-4 flex gap-2"><button type="button" onClick={props.onRetry} className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50"><RotateCcw className="h-4 w-4" />重新尝试</button><button type="button" onClick={props.onResetPlan} className="rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-50">修改问题</button></div></div></div></Assistant>}
  </div>;
}

function Assistant({ children }: { children: React.ReactNode }) { return <article className="flex items-start gap-4" aria-label="AI 分析回复"><span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-zinc-900 text-white"><Sparkles className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="mb-3 text-sm font-semibold text-zinc-900">AI 分析</div>{children}</div></article>; }

function Result({ result, stepCount }: { result: ResearchResult; stepCount: number }) {
  return <div><p className="text-[15px] leading-7 text-zinc-800">{result.summary}</p>{stepCount > 0 && <button type="button" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-zinc-600">已完成 {stepCount} 个分析步骤<ChevronDown className="h-4 w-4" /></button>}
    <div className="mt-5 divide-y divide-zinc-200 border-y border-zinc-200">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} aria-label={`${item.name} ${item.code}`} className="group grid gap-3 py-4 sm:grid-cols-[minmax(140px,.8fr)_minmax(0,1.5fr)_auto] sm:items-center"><div><span className="font-medium text-zinc-900">{item.name}</span><span className="ml-2 font-mono text-xs text-zinc-400">{item.code}</span></div><p className="text-sm leading-6 text-zinc-500">{item.reason}</p><div className="flex items-center gap-2 text-xs text-zinc-600"><span className="rounded-md bg-zinc-100 px-2 py-1">PE {item.pe_ttm ?? "—"}</span><span className="rounded-md bg-zinc-100 px-2 py-1">股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</span><ArrowRight className="ml-1 h-4 w-4 text-zinc-300 group-hover:text-zinc-700" /></div></Link>)}</div>
    <Link to={`/research/result/${result.task_id}`} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-teal-700">查看完整分析<ArrowRight className="h-4 w-4" /></Link>
    <div className="mt-5 flex gap-1 text-zinc-400"><button type="button" aria-label="复制回答" className="rounded-lg p-2 hover:bg-zinc-100 hover:text-zinc-700"><Copy className="h-4 w-4" /></button><button type="button" aria-label="重新生成" className="rounded-lg p-2 hover:bg-zinc-100 hover:text-zinc-700"><RefreshCw className="h-4 w-4" /></button></div>
  </div>;
}
