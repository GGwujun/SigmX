import { AlertCircle, ArrowRight, Check, Copy, LoaderCircle, RefreshCw, RotateCcw, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import type { ResearchConversationTurn, ResearchEvent, ResearchResult, ResearchStep, ResearchTask } from "@/lib/researchApi";

interface Props { turns: ResearchConversationTurn[]; pendingQuestion: string; planning: boolean; pendingError: string; loadError: string; onRetry: (task: ResearchTask) => void }

function safeActivity(events: ResearchEvent[]) {
  const messages: string[] = [];
  for (const event of events) {
    let message = "";
    if (event.type === "queued") message = "研究任务已进入执行队列";
    else if (event.type === "running") message = "正在检索和核验证据";
    else if (event.type === "tool_call" || event.type === "tool_started") message = "正在查询研究数据";
    else if (event.type === "tool_progress") message = "正在获取并解析数据";
    else if (event.type === "tool_result" || event.type === "tool_completed") message = event.payload.status === "error" ? "部分数据源暂不可用，正在尝试其他来源" : "已获取一批可用数据";
    else if (event.type === "llm_usage") message = "正在整理和分析数据";
    else if (event.type === "runtime_completed" || event.type === "completed") message = "分析完成，正在生成结论";
    if (message && messages[messages.length - 1] !== message) messages.push(message);
  }
  return messages.slice(-5);
}

function progressStage(events: ResearchEvent[]) {
  if (events.some(event => ["runtime_completed", "completed"].includes(event.type))) return 4;
  if (events.some(event => ["tool_result", "tool_completed", "llm_usage"].includes(event.type))) return 3;
  if (events.some(event => ["tool_call", "tool_started", "tool_progress"].includes(event.type))) return 2;
  if (events.some(event => event.type === "running")) return 1;
  return 0;
}

export function AIAnalysisTimeline({ turns, pendingQuestion, planning, pendingError, loadError, onRetry }: Props) {
  if (!turns.length && !pendingQuestion) return <div className="mx-auto flex min-h-[480px] max-w-2xl flex-col items-center justify-center px-6 pb-28 text-center"><span className="grid h-10 w-10 place-items-center rounded-full bg-zinc-950 text-white shadow-[0_1px_2px_rgba(0,0,0,.16)]"><Sparkles className="h-[18px] w-[18px] stroke-[1.8]" /></span><h2 className="mt-5 text-[24px] font-semibold leading-8 tracking-[-0.035em] text-zinc-950">今天想分析什么？</h2><p className="mt-2.5 max-w-xl text-[14px] leading-6 text-zinc-500">描述你关注的股票、行业或筛选条件，我会查询数据、核验证据并直接给出分析。</p>{loadError && <p className="mt-5 text-sm text-amber-700">部分市场信息暂时不可用，但仍可继续创建分析。</p>}</div>;
  return <div className="mx-4 space-y-10 py-9 pb-10 sm:mx-8 lg:mx-12 xl:mx-20 2xl:mx-24">{turns.map(turn => <ConversationTurn key={turn.task.id} turn={turn} onRetry={onRetry} />)}{pendingQuestion && <><UserMessage>{pendingQuestion}</UserMessage><Assistant>{planning ? <><p className="text-[14px] leading-6 text-zinc-800">正在理解你的问题</p><p className="mt-1 text-[13px] leading-5 text-zinc-500">接下来会自动查询数据并完成分析</p></> : <ErrorReply message={pendingError || "暂时无法开始本次分析，请稍后再试。"} />}</Assistant></>}</div>;
}

function ConversationTurn({ turn, onRetry }: { turn: ResearchConversationTurn; onRetry: (task: ResearchTask) => void }) {
  return <><UserMessage>{turn.task.question}</UserMessage><Assistant>{turn.result ? <Result result={turn.result} /> : turn.task.status === "failed" ? <ErrorReply message={turn.task.error || "分析执行失败"} onRetry={() => onRetry(turn.task)} /> : <RunningProgress steps={turn.task.steps} events={turn.events} />}</Assistant></>;
}

function UserMessage({ children }: { children: React.ReactNode }) { return <div className="flex justify-end"><div className="max-w-[78%] rounded-[22px] bg-[#f3f3f3] px-[18px] py-[11px] text-[14px] leading-[22px] text-zinc-900">{children}</div></div>; }
function Assistant({ children }: { children: React.ReactNode }) { return <article className="flex items-start gap-3.5" aria-label="AI 分析回复"><span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-zinc-950 text-white shadow-[0_1px_2px_rgba(0,0,0,.14)]"><Sparkles className="h-[14px] w-[14px] stroke-[1.8]" /></span><div className="min-w-0 flex-1 pt-0.5"><div className="mb-3 text-[13px] font-semibold tracking-[-0.01em] text-zinc-950">AI 分析</div>{children}</div></article>; }

function RunningProgress({ steps, events }: { steps: ResearchStep[]; events: ResearchEvent[] }) {
  const activity = safeActivity(events);
  const stage = progressStage(events);
  const currentActivity = activity[activity.length - 1];
  const fallback = steps.length ? steps : [{ key: "interpret", label: "理解研究问题", status: "pending" }, { key: "search", label: "查询研究数据", status: "pending" }, { key: "verify", label: "分析并核验证据", status: "pending" }, { key: "answer", label: "生成分析结论", status: "pending" }];
  return <>
    <p className="flex items-center gap-2 text-[14px] text-zinc-800"><LoaderCircle className="h-4 w-4 animate-spin text-zinc-500" />{currentActivity || "正在准备分析"}</p>
    <div className="mt-4 divide-y divide-zinc-100 border-y border-zinc-100">{fallback.map((step, index) => {
      const completed = step.status === "completed" || step.status === "succeeded" || index < stage;
      const active = !completed && index === stage;
      return <div key={step.key} className={`flex items-center gap-3 py-3 text-[13px] ${completed ? "text-zinc-800" : active ? "text-zinc-700" : "text-zinc-400"}`}><span className={`grid h-5 w-5 place-items-center rounded-full text-[10px] ${completed ? "bg-zinc-900 text-white" : active ? "bg-zinc-200 text-zinc-700" : "bg-zinc-100 text-zinc-400"}`}>{completed ? <Check className="h-3 w-3" /> : index + 1}</span><span className="flex-1">{step.label}</span>{active && <span className="text-[11px] text-zinc-400">进行中</span>}</div>;
    })}</div>
    {activity.length > 1 && <div aria-label="实时分析进度" className="mt-3 space-y-1.5">{activity.map((message, index) => <p key={`${index}-${message}`} className="text-[12px] leading-5 text-zinc-500">{message}</p>)}</div>}
  </>;
}

function ErrorReply({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="flex items-start gap-3 text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="font-semibold">分析没有完成</h2><p className="mt-2 text-sm leading-6 text-zinc-600">{message}</p>{onRetry && <button type="button" onClick={onRetry} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50"><RotateCcw className="h-4 w-4" />重新尝试</button>}</div></div>; }

function Result({ result }: { result: ResearchResult }) {
  return <div><p className="text-[14px] leading-7 text-zinc-800">{result.summary}</p>{result.conclusions?.length ? <div className="mt-4 space-y-2">{result.conclusions.map((item, index) => <p key={index} className="text-[13px] leading-6 text-zinc-600">{item.text}</p>)}</div> : null}<div className="mt-5 divide-y divide-zinc-200/80 border-y border-zinc-200/90">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} aria-label={`${item.name} ${item.code}`} className="group -mx-2 grid gap-2.5 rounded-lg px-2 py-4 transition-colors hover:bg-zinc-50 sm:grid-cols-[minmax(132px,.75fr)_minmax(0,1.45fr)_auto] sm:items-center"><div><span className="text-[14px] font-medium text-zinc-950">{item.name}</span><span className="ml-2 font-mono text-[11px] text-zinc-400">{item.code}</span></div><p className="text-[13px] leading-[22px] text-zinc-500">{item.reason}</p><div className="flex items-center gap-1.5 text-[11px] text-zinc-600"><span className="rounded-md bg-zinc-100/90 px-2 py-1">PE {item.pe_ttm ?? "—"}</span><span className="rounded-md bg-zinc-100/90 px-2 py-1">股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</span><ArrowRight className="ml-1 h-4 w-4 text-zinc-300 transition group-hover:translate-x-0.5 group-hover:text-zinc-700" /></div></Link>)}</div><div className="mt-5 flex gap-1 text-zinc-400"><button type="button" aria-label="复制回答" className="rounded-lg p-2 hover:bg-zinc-100 hover:text-zinc-700"><Copy className="h-4 w-4" /></button><button type="button" aria-label="重新生成" className="rounded-lg p-2 hover:bg-zinc-100 hover:text-zinc-700"><RefreshCw className="h-4 w-4" /></button></div></div>;
}
