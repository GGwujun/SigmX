import { useEffect, useState } from "react";
import { AlertCircle, ArrowRight, Check, ChevronDown, ChevronRight, Copy, Database, LoaderCircle, RefreshCw, RotateCcw, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { buildResearchConversation, stageLabel, type FinalConversationBlock, type ResearchConversationBlock, type StageConversationBlock, type ToolConversationBlock } from "@/lib/researchConversation";
import type { ResearchConversationTurn, ResearchResult, ResearchTask } from "@/lib/researchApi";

interface Props { turns: ResearchConversationTurn[]; pendingQuestion: string; planning: boolean; pendingError: string; loadError: string; onRetry: (task: ResearchTask) => void }

export function AIAnalysisTimeline({ turns, pendingQuestion, planning, pendingError, loadError, onRetry }: Props) {
  if (!turns.length && !pendingQuestion) return <Welcome loadError={loadError} />;
  return <div data-testid="conversation-stream" className="mx-auto w-full max-w-[760px] space-y-7 px-5 pb-8 pt-5 sm:px-7 lg:pt-6">
    {turns.map(turn => <ConversationTurn key={turn.task.id} turn={turn} onRetry={onRetry} />)}
    {pendingQuestion && <><UserMessage>{pendingQuestion}</UserMessage><Assistant>{planning ? <WaitingNote /> : <ErrorReply message={pendingError || "暂时无法开始本次分析，请稍后再试。"} />}</Assistant></>}
  </div>;
}

function Welcome({ loadError }: { loadError: string }) {
  return <div className="relative mx-auto flex h-full min-h-[380px] max-w-2xl flex-col items-center justify-center px-6 pb-14 pt-10 text-center">
    <span aria-hidden="true" className="aiw-hero pointer-events-none absolute inset-0" />
    <div className="relative flex flex-col items-center">
      <span className="grid h-[52px] w-[52px] place-items-center rounded-2xl bg-gradient-to-br from-teal-300 to-cyan-500 text-[#03211d] shadow-[0_0_44px_rgba(45,212,191,.28)]"><Sparkles className="h-[22px] w-[22px] stroke-[1.8]" /></span>
      <p className="mt-7 text-[11px] font-semibold uppercase tracking-[0.26em] text-teal-300">SigmX Research Agent</p>
      <h2 className="mt-3.5 text-[26px] font-semibold leading-9 tracking-[-0.02em] text-slate-50">今天想分析什么？</h2>
      <p className="mt-4 max-w-xl text-[14px] leading-[1.75] text-slate-400">描述你关注的股票、行业或筛选条件，我会查询数据、核验证据并直接给出分析。</p>
      {loadError && <p className="mt-5 rounded-lg border border-amber-400/25 bg-amber-400/[0.07] px-3.5 py-2 text-[13px] text-amber-300">部分市场信息暂时不可用，但仍可继续创建分析。</p>}
    </div>
  </div>;
}

/** 规划等待只报墙上时钟，不虚构进度（学习 VR AiWaiting 的诚实等待指示）。 */
function WaitingNote() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <div className="text-[13px] text-slate-400">
    <p className="flex items-center gap-2"><LoaderCircle className="h-4 w-4 animate-spin text-teal-300" />正在理解你的问题<span aria-live="off" className="tabular-nums text-slate-500"> · 已等待 {seconds} 秒</span></p>
    {seconds >= 30 && <p role="status" className="mt-1.5 text-[12px] leading-5 text-slate-500">研究管线会查询多路数据并核验证据，耗时较长属正常，请稍候。</p>}
  </div>;
}

function ConversationTurn({ turn, onRetry }: { turn: ResearchConversationTurn; onRetry: (task: ResearchTask) => void }) {
  const blocks = buildResearchConversation(turn.events, turn.result);
  const running = ["queued", "running"].includes(turn.task.status);
  const processBlocks = blocks.filter(block => block.kind !== "final");
  const finalBlocks = blocks.filter((block): block is FinalConversationBlock => block.kind === "final");
  return <section className="aiw-enter space-y-4"><UserMessage>{turn.task.question}</UserMessage><Assistant>
    {turn.task.status === "failed" ? <ErrorReply message={turn.task.error || "分析执行失败"} onRetry={() => onRetry(turn.task)} /> : <>
      {processBlocks.length > 0 ? <AnalysisProcess blocks={processBlocks} running={running} completed={finalBlocks.length > 0} /> : running ? <div className="flex items-center gap-2 text-[13px] text-slate-500"><LoaderCircle className="h-3.5 w-3.5 animate-spin text-teal-300" />正在准备分析</div> : null}
      {finalBlocks.map(block => <FinalReply key={block.id} block={block} onRetry={() => onRetry(turn.task)} />)}
    </>}
  </Assistant></section>;
}

function AnalysisProcess({ blocks, running, completed }: { blocks: Exclude<ResearchConversationBlock, FinalConversationBlock>[]; running: boolean; completed: boolean }) {
  const [expanded, setExpanded] = useState(running || !completed);
  useEffect(() => { if (running) setExpanded(true); else if (completed) setExpanded(false); }, [running, completed]);
  const status = running ? "进行中" : completed ? "已完成" : "已暂停";
  const lastAssistantId = [...blocks].reverse().find(block => block.kind === "assistant")?.id;
  return <div className="overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.025]"><button type="button" aria-label={`分析过程，${status}`} aria-expanded={expanded} onClick={() => setExpanded(value => !value)} className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-[12px] transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-400/40"><span className="grid h-4 w-4 place-items-center">{running ? <LoaderCircle className="h-3.5 w-3.5 animate-spin text-teal-300" /> : <Check className="h-3.5 w-3.5 text-emerald-400" />}</span><span className="font-medium text-slate-300">分析过程</span><span className="text-slate-500">{status}</span><span className="ml-auto text-slate-500">{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</span></button>{expanded && <div className="border-t border-white/[0.06] px-3.5 py-3"><div className="space-y-2.5 border-l border-white/[0.08] pl-4">{blocks.map(block => block.kind === "assistant" ? <p key={block.id} className="whitespace-pre-wrap text-[13px] leading-[1.65] tracking-[-0.003em] text-slate-400">{block.text}{running && block.id === lastAssistantId && <StreamingCursor />}</p> : block.kind === "stage" ? <StageDetail key={block.id} block={block} /> : <ToolDetail key={block.id} block={block} />)}</div></div>}</div>;
}

function StreamingCursor() { return <span data-testid="assistant-streaming-cursor" aria-hidden="true" className="ml-1 inline-block h-[1.05em] w-[2px] animate-pulse translate-y-[2px] bg-teal-300" />; }

function UserMessage({ children }: { children: React.ReactNode }) { return <div className="flex justify-end"><div className="max-w-[84%] rounded-[18px] rounded-br-md border border-white/[0.08] bg-[#18222e] px-4 py-2.5 text-[13.5px] leading-6 text-slate-100 shadow-[0_2px_12px_rgba(0,0,0,.28)] sm:max-w-[72%]">{children}</div></div>; }
function Assistant({ children }: { children: React.ReactNode }) { return <article aria-label="AI 分析回复" className="space-y-3.5"><header className="flex items-center gap-2.5"><span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-teal-300 to-cyan-500 text-[#03211d] shadow-[0_0_14px_rgba(45,212,191,.32)]"><Sparkles className="h-[15px] w-[15px]" /></span><span className="text-[12.5px] font-semibold tracking-[0.01em] text-slate-300">SigmX Research</span></header>{children}</article>; }

function ToolDetail({ block }: { block: ToolConversationBlock }) {
  const status = block.status === "running" ? "进行中" : block.status === "error" ? "失败" : block.evidenceCount == null ? "完成" : `${block.evidenceCount} 条证据`;
  return <div className="flex flex-wrap items-center gap-x-2 text-[11px] leading-5 text-slate-500"><span className="inline-flex items-center gap-1.5 font-medium text-slate-400"><Database className="h-3 w-3 text-slate-500" />{block.label}</span><span className={block.evidenceCount != null && block.status !== "error" && block.status !== "running" ? "text-teal-300/90" : undefined}>{status}</span>{block.elapsedMs != null && <span className="tabular-nums text-slate-600">{(block.elapsedMs / 1000).toFixed(1)} 秒</span>}</div>;
}

function StageDetail({ block }: { block: StageConversationBlock }) {
  const status = block.status === "running" ? "进行中" : block.status === "error" ? "失败" : block.partial ? "部分完成" : "完成";
  return <div className="space-y-1">
    <div className="flex items-center gap-2 text-[12px] leading-5">
      <span className={block.status === "error" ? "text-red-400" : block.status === "running" ? "text-teal-300" : "text-emerald-400"}>{block.status === "running" ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : block.status === "error" ? <AlertCircle className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />}</span>
      <span className="font-medium text-slate-300">{stageLabel(block.stage)}</span>
      <span className={block.status === "error" ? "text-red-300" : "text-slate-500"}>{status}</span>
    </div>
    {block.gaps?.length ? <p className="pl-[22px] text-[11px] leading-4 text-amber-300/90">数据缺口：{block.gaps.join("；")}</p> : null}
  </div>;
}

function FinalReply({ block, onRetry }: { block: FinalConversationBlock; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const plainText = [block.summary, ...block.conclusions.map(item => item.text), ...block.risks.map(risk => `风险提示：${risk}`)].join("\n\n");
  const copy = async () => {
    try { await navigator.clipboard.writeText(plainText); setCopied(true); window.setTimeout(() => setCopied(false), 1600); } catch { /* 剪贴板不可用时静默 */ }
  };
  return <div className="space-y-4">
    <div className="flex items-center gap-3"><h2 className="text-[15px] font-semibold tracking-[-0.01em] text-slate-100">分析结论</h2><span aria-hidden="true" className="h-px flex-1 bg-gradient-to-r from-teal-400/45 via-white/[0.08] to-transparent" /></div>
    <p className="text-[14.5px] leading-[1.75] text-slate-200">{block.summary}</p>
    {block.conclusions.length > 0 && <div className="space-y-2">{block.conclusions.map((item, index) => <div key={index} className="rounded-xl border border-l-2 border-white/[0.06] border-l-teal-400/70 bg-white/[0.02] px-4 py-3"><p className="text-[13.5px] leading-[1.7] text-slate-300">{item.stage && <span className="mr-2 inline-block rounded-md border border-teal-400/20 bg-teal-400/[0.08] px-1.5 py-0.5 align-[1px] text-[10.5px] font-medium text-teal-300">{stageLabel(item.stage)}</span>}{item.text}</p></div>)}</div>}
    {block.risks.length > 0 && <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.05] px-4 py-3"><h3 className="flex items-center gap-1.5 text-[12.5px] font-semibold text-amber-300"><AlertCircle className="h-3.5 w-3.5" />风险提示</h3><ul className="mt-1.5 list-disc space-y-1 pl-5 text-[12.5px] leading-6 text-amber-100/75">{block.risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul></div>}
    {block.result && <CandidateList result={block.result} />}
    <div className="flex items-center gap-1">
      <button type="button" aria-label="复制回答" onClick={copy} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-teal-300">{copied ? <Check className="h-3.5 w-3.5 text-teal-300" /> : <Copy className="h-3.5 w-3.5" />}{copied && "已复制"}</button>
      {onRetry && <button type="button" aria-label="重新生成" onClick={onRetry} className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-teal-300"><RefreshCw className="h-3.5 w-3.5" /></button>}
    </div>
  </div>;
}

function CandidateList({ result }: { result: ResearchResult }) {
  if (!result.candidates.length) return null;
  return <div className="space-y-2">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} aria-label={`${item.name} ${item.code}`} className="group grid gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3.5 transition-colors hover:border-teal-400/35 hover:bg-teal-400/[0.04] sm:grid-cols-[minmax(132px,.75fr)_minmax(0,1.45fr)_auto] sm:items-center"><div><span className="text-[14px] font-medium text-slate-100">{item.name}</span><span className="ml-2 font-mono text-[11px] text-teal-300/70">{item.code}</span></div><p className="text-[13px] leading-[22px] text-slate-400">{item.reason}</p><div className="flex items-center gap-1.5 font-mono text-[11px] tabular-nums text-slate-300"><span className="rounded-md border border-white/[0.07] bg-white/[0.03] px-2 py-1">PE {item.pe_ttm ?? "—"}</span><span className="rounded-md border border-white/[0.07] bg-white/[0.03] px-2 py-1">股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</span><ArrowRight className="ml-1 h-4 w-4 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-teal-300" /></div></Link>)}</div>;
}

function ErrorReply({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="rounded-xl border border-red-400/25 bg-red-400/[0.06] px-4 py-3.5"><div className="flex items-start gap-3"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" /><div><h2 className="font-semibold text-red-200">分析没有完成</h2><p className="mt-1.5 text-[13px] leading-6 text-slate-300">{message}</p>{onRetry && <button type="button" onClick={onRetry} className="mt-3.5 inline-flex items-center gap-2 rounded-lg border border-red-300/30 px-3 py-2 text-[13px] font-medium text-red-200 transition-colors hover:bg-red-400/10"><RotateCcw className="h-4 w-4" />重新尝试</button>}</div></div></div>; }
