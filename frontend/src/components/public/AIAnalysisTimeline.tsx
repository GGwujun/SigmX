import { useEffect, useState } from "react";
import { AlertCircle, ArrowRight, Check, ChevronDown, ChevronRight, Copy, Database, LoaderCircle, RefreshCw, RotateCcw, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { buildResearchConversation, type FinalConversationBlock, type ResearchConversationBlock, type ToolConversationBlock } from "@/lib/researchConversation";
import type { ResearchConversationTurn, ResearchResult, ResearchTask } from "@/lib/researchApi";

interface Props { turns: ResearchConversationTurn[]; pendingQuestion: string; planning: boolean; pendingError: string; loadError: string; onRetry: (task: ResearchTask) => void }

export function AIAnalysisTimeline({ turns, pendingQuestion, planning, pendingError, loadError, onRetry }: Props) {
  if (!turns.length && !pendingQuestion) return <Welcome loadError={loadError} />;
  return <div data-testid="conversation-stream" className="mx-auto w-full max-w-[760px] space-y-6 px-5 pb-8 pt-5 sm:px-7 lg:pt-6">
    {turns.map(turn => <ConversationTurn key={turn.task.id} turn={turn} onRetry={onRetry} />)}
    {pendingQuestion && <><UserMessage>{pendingQuestion}</UserMessage><Assistant>{planning ? <div className="flex items-center gap-2 text-[15px] leading-7 text-zinc-700"><LoaderCircle className="h-4 w-4 animate-spin text-zinc-400" />正在理解你的问题</div> : <ErrorReply message={pendingError || "暂时无法开始本次分析，请稍后再试。"} />}</Assistant></>}
  </div>;
}

function Welcome({ loadError }: { loadError: string }) {
  return <div className="mx-auto flex min-h-[360px] max-w-2xl flex-col items-center justify-center px-6 pb-10 pt-12 text-center sm:min-h-[420px]"><span className="grid h-10 w-10 place-items-center rounded-full bg-zinc-950 text-white shadow-[0_1px_2px_rgba(0,0,0,.16)]"><Sparkles className="h-[18px] w-[18px] stroke-[1.8]" /></span><h2 className="mt-5 text-[24px] font-semibold leading-8 tracking-[-0.035em] text-zinc-950">今天想分析什么？</h2><p className="mt-2.5 max-w-xl text-[14px] leading-6 text-zinc-500">描述你关注的股票、行业或筛选条件，我会查询数据、核验证据并直接给出分析。</p>{loadError && <p className="mt-5 text-sm text-amber-700">部分市场信息暂时不可用，但仍可继续创建分析。</p>}</div>;
}

function ConversationTurn({ turn, onRetry }: { turn: ResearchConversationTurn; onRetry: (task: ResearchTask) => void }) {
  const blocks = buildResearchConversation(turn.events, turn.result);
  const running = ["queued", "running"].includes(turn.task.status);
  const processBlocks = blocks.filter(block => block.kind !== "final");
  const finalBlocks = blocks.filter((block): block is FinalConversationBlock => block.kind === "final");
  return <section className="space-y-4"><UserMessage>{turn.task.question}</UserMessage><Assistant>
    {turn.task.status === "failed" ? <ErrorReply message={turn.task.error || "分析执行失败"} onRetry={() => onRetry(turn.task)} /> : <>
      {processBlocks.length > 0 ? <AnalysisProcess blocks={processBlocks} running={running} completed={finalBlocks.length > 0} /> : running ? <div className="flex items-center gap-2 text-[13px] text-zinc-500"><LoaderCircle className="h-3.5 w-3.5 animate-spin text-zinc-400" />正在准备分析</div> : null}
      {finalBlocks.map(block => <FinalReply key={block.id} block={block} />)}
    </>}
  </Assistant></section>;
}

function AnalysisProcess({ blocks, running, completed }: { blocks: Exclude<ResearchConversationBlock, FinalConversationBlock>[]; running: boolean; completed: boolean }) {
  const [expanded, setExpanded] = useState(running || !completed);
  useEffect(() => { if (running) setExpanded(true); else if (completed) setExpanded(false); }, [running, completed]);
  const status = running ? "进行中" : completed ? "已完成" : "已暂停";
  const lastAssistantId = [...blocks].reverse().find(block => block.kind === "assistant")?.id;
  return <div className="rounded-xl bg-zinc-50/80 px-3.5 py-2.5"><button type="button" aria-label={`分析过程，${status}`} aria-expanded={expanded} onClick={() => setExpanded(value => !value)} className="flex w-full items-center gap-2 text-left text-[12px] text-zinc-500 transition-colors hover:text-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-300"><span className="grid h-4 w-4 place-items-center">{running ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}</span><span className="font-medium text-zinc-700">分析过程</span><span className="text-zinc-400">{status}</span><span className="ml-auto">{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</span></button>{expanded && <div className="mt-2.5 space-y-2.5 border-l border-zinc-200 pl-3.5">{blocks.map(block => block.kind === "assistant" ? <p key={block.id} className="whitespace-pre-wrap text-[13px] leading-[1.65] tracking-[-0.003em] text-zinc-600">{block.text}{running && block.id === lastAssistantId && <StreamingCursor />}</p> : <ToolDetail key={block.id} block={block} />)}</div>}</div>;
}

function StreamingCursor() { return <span data-testid="assistant-streaming-cursor" aria-hidden="true" className="ml-1 inline-block h-[1.05em] w-[2px] animate-pulse translate-y-[2px] bg-zinc-800" />; }

function UserMessage({ children }: { children: React.ReactNode }) { return <div className="flex justify-end"><div className="max-w-[84%] rounded-[16px] bg-zinc-100 px-3.5 py-2 text-[13px] leading-5 text-zinc-900 sm:max-w-[70%]">{children}</div></div>; }
function Assistant({ children }: { children: React.ReactNode }) { return <article aria-label="AI 分析回复" className="space-y-3">{children}</article>; }

function ToolDetail({ block }: { block: ToolConversationBlock }) {
  const status = block.status === "running" ? "进行中" : block.status === "error" ? "失败" : block.evidenceCount == null ? "完成" : `${block.evidenceCount} 条证据`;
  return <div className="flex flex-wrap items-center gap-x-2 text-[11px] leading-5 text-zinc-500"><span className="inline-flex items-center gap-1.5 font-medium text-zinc-600"><Database className="h-3 w-3 text-zinc-400" />{block.label}</span><span>{status}</span>{block.elapsedMs != null && <span className="text-zinc-400">{(block.elapsedMs / 1000).toFixed(1)} 秒</span>}</div>;
}

function FinalReply({ block }: { block: FinalConversationBlock }) {
  return <div className="space-y-3.5 pt-1"><h2 className="text-[16px] font-semibold tracking-[-0.018em] text-zinc-950">分析结论</h2><p className="text-[14px] leading-[1.7] text-zinc-800">{block.summary}</p>{block.conclusions.length > 0 && <div className="space-y-2">{block.conclusions.map((item, index) => <p key={index} className="text-[14px] leading-[1.7] text-zinc-700">{item.text}</p>)}</div>}{block.risks.length > 0 && <div><h3 className="text-[13px] font-semibold text-zinc-900">风险提示</h3><ul className="mt-1.5 list-disc space-y-1 pl-5 text-[12px] leading-6 text-zinc-600">{block.risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul></div>}{block.result && <CandidateList result={block.result} />}<div className="flex gap-1 pt-0.5 text-zinc-400"><button type="button" aria-label="复制回答" className="rounded-lg p-1.5 hover:bg-zinc-100 hover:text-zinc-700"><Copy className="h-3.5 w-3.5" /></button><button type="button" aria-label="重新生成" className="rounded-lg p-1.5 hover:bg-zinc-100 hover:text-zinc-700"><RefreshCw className="h-3.5 w-3.5" /></button></div></div>;
}

function CandidateList({ result }: { result: ResearchResult }) {
  if (!result.candidates.length) return null;
  return <div className="divide-y divide-zinc-200/80 border-y border-zinc-200/90">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} aria-label={`${item.name} ${item.code}`} className="group -mx-2 grid gap-2.5 rounded-lg px-2 py-4 transition-colors hover:bg-zinc-50 sm:grid-cols-[minmax(132px,.75fr)_minmax(0,1.45fr)_auto] sm:items-center"><div><span className="text-[14px] font-medium text-zinc-950">{item.name}</span><span className="ml-2 font-mono text-[11px] text-zinc-400">{item.code}</span></div><p className="text-[13px] leading-[22px] text-zinc-500">{item.reason}</p><div className="flex items-center gap-1.5 text-[11px] text-zinc-600"><span className="rounded-md bg-zinc-100/90 px-2 py-1">PE {item.pe_ttm ?? "—"}</span><span className="rounded-md bg-zinc-100/90 px-2 py-1">股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</span><ArrowRight className="ml-1 h-4 w-4 text-zinc-300 transition group-hover:translate-x-0.5 group-hover:text-zinc-700" /></div></Link>)}</div>;
}

function ErrorReply({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="flex items-start gap-3 text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="font-semibold">分析没有完成</h2><p className="mt-2 text-sm leading-6 text-zinc-600">{message}</p>{onRetry && <button type="button" onClick={onRetry} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50"><RotateCcw className="h-4 w-4" />重新尝试</button>}</div></div>; }
