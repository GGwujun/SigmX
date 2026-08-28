import { AlertCircle, ArrowRight, Check, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ResearchPlanPanel } from "./ResearchPlanPanel";
import type { ResearchPlan, ResearchResult, ResearchTask } from "@/lib/researchApi";

export type AIAnalysisRunState = "idle" | "planning" | "plan" | "running" | "done" | "error";
export interface ResearchEvent { id: number; type: string; payload: Record<string, unknown> }

interface Props {
  phase: AIAnalysisRunState;
  question: string;
  plan: ResearchPlan | null;
  task: ResearchTask | null;
  events: ResearchEvent[];
  result: ResearchResult | null;
  loadError: string;
  runError: string;
  onRun: () => void;
  onRetry: () => void;
  onUseSuggested: (question: string) => void;
  onResetPlan: () => void;
}

export function AIAnalysisTimeline(props: Props) {
  const { phase, question, plan, task, result, loadError, runError } = props;
  if (phase === "idle") return <div className="mx-auto flex min-h-[500px] max-w-2xl flex-col items-center justify-center px-6 pb-28 text-center">
    <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary"><Sparkles className="h-6 w-6" /></span>
    <h2 className="mt-5 text-2xl font-semibold tracking-tight">今天想分析什么？</h2>
    <p className="mt-3 max-w-lg text-sm leading-6 text-slate-500">描述你关注的股票、行业或筛选条件，我会先整理研究计划，再逐步完成分析。</p>
    {loadError && <p className="mt-6 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">部分市场信息暂时不可用，但仍可继续创建分析。</p>}
  </div>;

  return <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-8 pb-32 sm:px-7">
    {question && <UserMessage>{question}</UserMessage>}
    {phase === "planning" && <AssistantMessage><ProgressTitle icon={<LoaderCircle className="h-4 w-4 animate-spin" />} title="正在理解你的研究问题" subtitle="马上为你整理可确认的分析步骤" /></AssistantMessage>}
    {phase === "plan" && plan && <AssistantMessage><p className="mb-4 text-sm font-medium text-slate-800">我整理了一份研究计划</p><ResearchPlanPanel plan={plan} onUseSuggested={props.onUseSuggested} onRun={props.onRun} onClose={props.onResetPlan} /></AssistantMessage>}
    {phase === "running" && <AssistantMessage><ProgressTitle icon={<LoaderCircle className="h-4 w-4 animate-spin" />} title="正在分析市场数据" subtitle="我会完成筛选、核验并整理结论" /><div className="mt-5 space-y-2">{(task?.steps ?? plan?.steps ?? []).map((step, index) => {
      const completed = step.status === "completed" || step.status === "succeeded";
      return <div key={step.key} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm"><span className={`grid h-6 w-6 place-items-center rounded-full ${completed ? "bg-emerald-100 text-emerald-700" : "bg-primary/10 text-primary"}`}>{completed ? <Check className="h-3.5 w-3.5" /> : index + 1}</span><span className="text-slate-700">{step.label}</span></div>;
    })}</div></AssistantMessage>}
    {phase === "done" && result && <AssistantMessage><ResultCards result={result} /></AssistantMessage>}
    {phase === "error" && <AssistantMessage><div className="rounded-2xl border border-red-100 bg-red-50/70 p-5"><AlertCircle className="h-6 w-6 text-red-500" /><h2 className="mt-3 text-lg font-semibold">分析没有完成</h2><p className="mt-2 text-sm text-slate-600">{runError || "暂时无法完成本次分析，请稍后再试。"}</p><div className="mt-5 flex flex-wrap gap-3"><button type="button" onClick={props.onRetry} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"><RotateCcw className="h-4 w-4" />重新尝试</button><button type="button" onClick={props.onResetPlan} className="rounded-lg border bg-white px-4 py-2 text-sm font-semibold text-slate-700">修改问题</button></div></div></AssistantMessage>}
  </div>;
}

function UserMessage({ children }: { children: string }) {
  return <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-tr-md bg-slate-900 px-4 py-3 text-sm leading-6 text-white shadow-sm">{children}</div></div>;
}

function AssistantMessage({ children }: { children: React.ReactNode }) {
  return <div className="flex items-start gap-3"><span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-primary text-white"><Sparkles className="h-4 w-4" /></span><div className="min-w-0 flex-1">{children}</div></div>;
}

function ProgressTitle({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center gap-2 font-semibold text-slate-900"><span className="text-primary">{icon}</span>{title}</div><p className="mt-2 text-sm text-slate-500">{subtitle}</p></div>;
}

function ResultCards({ result }: { result: ResearchResult }) {
  return <div><div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center gap-2 text-sm font-semibold text-emerald-700"><Check className="h-4 w-4" />分析完成</div><p className="mt-3 text-sm leading-6 text-slate-700">{result.summary}</p>{result.as_of && <p className="mt-2 text-xs text-slate-400">数据日期 {result.as_of}</p>}</div>
    <div className="mt-3 space-y-3">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} aria-label={`${item.name} ${item.code}`} className="block rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-primary/30 hover:shadow-md"><div className="flex items-start justify-between gap-4"><div><h3 className="font-semibold text-slate-900">{item.name} <span className="ml-1 font-mono text-xs font-normal text-slate-400">{item.code}</span></h3>{item.industry && <p className="mt-1 text-xs text-slate-400">{item.industry}</p>}</div><ArrowRight className="h-4 w-4 text-slate-300" /></div><p className="mt-3 text-sm leading-6 text-slate-600">{item.reason}</p><div className="mt-4 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-700">PE {item.pe_ttm ?? "—"}</span><span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-700">股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</span></div></Link>)}</div>
    <div className="mt-4 flex justify-end"><Link to={`/research/result/${result.task_id}`} className="inline-flex items-center gap-2 text-sm font-semibold text-primary">查看完整结果<ArrowRight className="h-4 w-4" /></Link></div>
  </div>;
}
