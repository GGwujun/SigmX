import { useEffect, useState, type FormEvent } from "react";
import { ArrowUp, LoaderCircle, Sparkles } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AIAnalysisShell } from "@/components/public/AIAnalysisShell";
import { AIAnalysisTimeline, type AIAnalysisRunState } from "@/components/public/AIAnalysisTimeline";
import { createResearchPlan, createResearchTask, getDiscovery, getResearchResult, listResearchEvents, listResearchTasks, waitForResearchTask, type PublicDiscovery, type ResearchPlan, type ResearchResult, type ResearchTask, type ResearchTemplate } from "@/lib/researchApi";
import { clearPendingResearchPlan, loadPendingResearchPlan, savePendingResearchPlan } from "@/lib/pendingResearchPlan";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

export function LandingPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [discovery, setDiscovery] = useState<PublicDiscovery | null>(null);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [template, setTemplate] = useState<ResearchTemplate | null>(null);
  const [phase, setPhase] = useState<AIAnalysisRunState>("idle");
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [runError, setRunError] = useState("");
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
  const [activeTask, setActiveTask] = useState<ResearchTask | null>(null);
  const [agentEvents, setAgentEvents] = useState<Array<{ id: number; type: string; payload: Record<string, unknown> }>>([]);

  useEffect(() => {
    trackPersonalFunnel("landing_view");
    getDiscovery().then(setDiscovery).catch((error: Error) => setLoadError(error.message));
    if (isAuthenticated()) listResearchTasks(20).then(setRecentTasks).catch(() => undefined);
    const pending = loadPendingResearchPlan();
    if (pending && isAuthenticated()) { setQuery(pending.question); setPlan(pending.plan); setPhase("plan"); }
  }, []);

  const resetConversation = () => { setQuery(""); setTemplate(null); setPlan(null); setResult(null); setActiveTask(null); setAgentEvents([]); setRunError(""); setPhase("idle"); clearPendingResearchPlan(); };
  const editQuestion = () => { setPlan(null); setResult(null); setActiveTask(null); setAgentEvents([]); setRunError(""); setPhase("idle"); clearPendingResearchPlan(); };
  const chooseTemplate = (item: ResearchTemplate) => { setTemplate(item); setQuery(item.prompt); setPlan(null); setResult(null); setPhase("idle"); };
  const buildPlan = async (question = query.trim(), templateId = template?.id ?? null) => {
    if (!question) return;
    setPhase("planning"); setRunError(""); setResult(null);
    try {
      const created = await createResearchPlan({ question, template_id: templateId, scope: { market: "A股", exclude_st: true } });
      setQuery(created.question); setPlan(created); setPhase("plan");
    } catch (error) { setRunError(error instanceof Error ? error.message : "研究计划生成失败"); setPhase("error"); }
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void buildPlan(); };
  const run = async () => {
    if (!plan?.executable) return;
    if (!isAuthenticated()) { savePendingResearchPlan({ question: plan.question, templateId: plan.template_id, plan }); navigate(`/login?next=${encodeURIComponent("/")}`); return; }
    setPhase("running"); setRunError("");
    try {
      const task = await createResearchTask({ question: plan.question, template_id: plan.template_id, scope: plan.scope, constraints: plan.constraints, plan });
      setActiveTask(task); clearPendingResearchPlan();
      const completedTask = await waitForResearchTask(task, current => { setActiveTask(current); void listResearchEvents(task.id).then(setAgentEvents).catch(() => undefined); });
      setActiveTask(completedTask); setAgentEvents(await listResearchEvents(task.id).catch(() => []));
      const completed = await getResearchResult(task.id);
      setResult(completed); setPhase("done"); setRecentTasks(current => [completedTask, ...current.filter(item => item.id !== completedTask.id)]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "研究运行失败";
      if (message === "登录已过期，请重新登录") { savePendingResearchPlan({ question: plan.question, templateId: plan.template_id, plan }); navigate(`/login?next=${encodeURIComponent("/")}`); return; }
      setRunError(message); setPhase("error");
    }
  };

  const templates = discovery?.templates ?? [];
  const showSuggestions = phase === "idle" && !query.trim();
  return <AIAnalysisShell recentTasks={recentTasks} activeTaskId={activeTask?.id ?? null} onNewAnalysis={resetConversation}>
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto"><AIAnalysisTimeline phase={phase} question={query} plan={plan} task={activeTask} events={agentEvents} result={result} loadError={loadError} runError={runError} onRun={run} onRetry={plan?.executable ? run : () => void buildPlan()} onUseSuggested={(question) => { setTemplate(null); void buildPlan(question, null); }} onResetPlan={editQuestion} /></div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white/95 to-transparent px-4 pb-5 pt-12 sm:px-7"><div className="pointer-events-auto mx-auto max-w-3xl">
        {showSuggestions && templates.length > 0 && <div className="mb-3 flex gap-2 overflow-x-auto pb-1">{templates.map(item => <button key={item.id} type="button" onClick={() => chooseTemplate(item)} className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 shadow-sm hover:border-primary/30 hover:text-primary">{item.label}</button>)}</div>}
        <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_10px_40px_rgba(15,23,42,0.12)] focus-within:border-primary/40"><div className="flex items-end gap-2"><span className="mb-2 ml-2 text-primary"><Sparkles className="h-4 w-4" /></span><textarea aria-label="研究问题" rows={1} value={query} onChange={event => { setQuery(event.target.value); setTemplate(null); if (phase !== "idle") editQuestion(); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="输入你想分析的股票、行业或条件…" className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-6 outline-none placeholder:text-slate-400" /><button type="submit" aria-label="生成研究计划" disabled={phase === "planning" || !query.trim()} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-white disabled:cursor-not-allowed disabled:opacity-40">{phase === "planning" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}</button></div><p className="px-2 pb-1 text-[11px] text-slate-400">AI 分析仅供研究参考，不构成投资建议</p></form>
      </div></div>
    </div>
  </AIAnalysisShell>;
}
