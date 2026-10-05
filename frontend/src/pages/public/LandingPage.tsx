import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp, LoaderCircle, Plus } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AIAnalysisShell } from "@/components/public/AIAnalysisShell";
import { AIAnalysisTimeline } from "@/components/public/AIAnalysisTimeline";
import { createResearchPlan, createResearchTask, followUpResearchTask, getDiscovery, getResearchResult, getResearchThread, listResearchEvents, listResearchTasks, streamResearchEvents, waitForResearchTask, type PublicDiscovery, type ResearchConversationTurn, type ResearchEvent, type ResearchPlan, type ResearchTask, type ResearchTemplate } from "@/lib/researchApi";
import { clearPendingResearchPlan, loadPendingResearchPlan, savePendingResearchPlan } from "@/lib/pendingResearchPlan";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

export function LandingPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [discovery, setDiscovery] = useState<PublicDiscovery | null>(null);
  const [loadError, setLoadError] = useState("");
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const [template, setTemplate] = useState<ResearchTemplate | null>(null);
  const [turns, setTurns] = useState<ResearchConversationTurn[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [planning, setPlanning] = useState(false);
  const [pendingError, setPendingError] = useState("");
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
  const restoredPending = useRef(false);
  const conversationId = params.get("conversation");
  const busy = planning || turns.some(turn => ["queued", "running"].includes(turn.task.status));

  useEffect(() => {
    trackPersonalFunnel("landing_view");
    getDiscovery().then(setDiscovery).catch((error: Error) => setLoadError(error.message));
    if (isAuthenticated()) listResearchTasks(20).then(setRecentTasks).catch(() => undefined);
  }, []);

  const updateTurn = useCallback((taskId: string, update: (turn: ResearchConversationTurn) => ResearchConversationTurn) => {
    setTurns(current => current.map(turn => turn.task.id === taskId ? update(turn) : turn));
  }, []);

  const monitorTask = useCallback(async (task: ResearchTask) => {
    // Events merge by database id so the SSE stream and the polling fallback
    // share one cursor without duplicating frames.
    let after = 0;
    const mergeEvents = (incoming: ResearchEvent[]) => {
      if (!incoming.length) return;
      after = Math.max(after, ...incoming.map(event => event.id));
      updateTurn(task.id, turn => {
        const seen = new Set(turn.events.map(event => event.id));
        const fresh = incoming.filter(event => !seen.has(event.id));
        return fresh.length ? { ...turn, events: [...turn.events, ...fresh] } : turn;
      });
    };
    // Live stream first (real-time model output); if it fails, fall back to
    // cursor polling inside the status loop below. While the stream is
    // healthy the status check drops to a slow 5s watchdog — all progress
    // arrives over SSE, no event polling.
    let streaming = true;
    void streamResearchEvents(task.id, 0, event => mergeEvents([event]))
      .catch(() => { streaming = false; });
    try {
      const completedTask = await waitForResearchTask(task, current => {
        updateTurn(task.id, turn => ({ ...turn, task: current }));
        if (!streaming) {
          void listResearchEvents(task.id, after).then(mergeEvents).catch(() => undefined);
        }
      }, () => (streaming ? 5000 : 700));
      const [tailEvents, result] = await Promise.all([
        listResearchEvents(task.id, after).catch(() => []),
        getResearchResult(task.id),
      ]);
      mergeEvents(tailEvents);
      updateTurn(task.id, turn => ({ ...turn, task: completedTask, result }));
      setRecentTasks(current => [completedTask, ...current.filter(item => item.id !== completedTask.id)]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "分析执行失败";
      updateTurn(task.id, turn => ({ ...turn, task: { ...turn.task, status: "failed", error: message } }));
    }
  }, [updateTurn]);

  useEffect(() => {
    if (!conversationId || !isAuthenticated()) { if (!conversationId) setTurns([]); return; }
    let cancelled = false;
    setLoadError("");
    getResearchThread(conversationId).then(thread => {
      if (cancelled) return;
      setTurns(thread.turns);
      // Re-attach to any turn still running (page reload mid-analysis).
      thread.turns.forEach(turn => {
        if (["queued", "running"].includes(turn.task.status)) void monitorTask(turn.task);
      });
    }).catch((error: Error) => { if (!cancelled) setLoadError(error.message); });
    return () => { cancelled = true; };
  }, [conversationId, monitorTask]);

  const executePlan = useCallback(async (plan: ResearchPlan) => {
    if (!plan.executable) {
      setPendingError(plan.conditions.find(condition => condition.status === "unavailable")?.reason || "当前问题暂时无法可靠执行，请换一种问法后再试。");
      setPlanning(false); return;
    }
    if (!isAuthenticated()) {
      savePendingResearchPlan({ question: plan.question, templateId: plan.template_id, plan });
      navigate(`/login?next=${encodeURIComponent("/")}`); return;
    }
    try {
      const task = await createResearchTask({ question: plan.question, template_id: plan.template_id, scope: plan.scope, constraints: plan.constraints, plan });
      setTurns(current => [...current, { task, events: [], result: null }]);
      setPendingQuestion(""); setPlanning(false); clearPendingResearchPlan();
      setParams({ conversation: task.id }, { replace: true });
      void monitorTask(task);
    } catch (error) {
      const message = error instanceof Error ? error.message : "研究运行失败";
      if (message === "登录已过期，请重新登录") {
        savePendingResearchPlan({ question: plan.question, templateId: plan.template_id, plan });
        navigate(`/login?next=${encodeURIComponent("/")}`); return;
      }
      setPendingError(message); setPlanning(false);
    }
  }, [monitorTask, navigate, setParams]);

  useEffect(() => {
    if (restoredPending.current || !isAuthenticated()) return;
    const pending = loadPendingResearchPlan();
    if (!pending) return;
    restoredPending.current = true; setPendingQuestion(pending.question); setPlanning(true); void executePlan(pending.plan);
  }, [executePlan]);

  const startAnalysis = async (question: string, templateId: string | null) => {
    if (!question || busy) return;
    setDraft(""); setPendingQuestion(question); setPlanning(true); setPendingError("");
    try {
      const plan = await createResearchPlan({ question, template_id: templateId, scope: { market: "A股", exclude_st: true } });
      await executePlan(plan);
    } catch (error) { setPendingError(error instanceof Error ? error.message : "暂时无法开始本次分析"); setPlanning(false); }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    const lastTurn = turns[turns.length - 1];
    if (lastTurn?.result) {
      setDraft(""); setPendingQuestion(question); setPlanning(true); setPendingError("");
      void followUpResearchTask(lastTurn.task.id, question).then(task => {
        setTurns(current => [...current, { task, events: [], result: null }]);
        setPendingQuestion(""); setPlanning(false); setParams({ conversation: task.id }, { replace: true }); void monitorTask(task);
      }).catch((error: Error) => { setPendingError(error.message); setPlanning(false); });
      return;
    }
    void startAnalysis(question, template?.id ?? null);
  };

  const resetConversation = () => { setDraft(""); setTemplate(null); setTurns([]); setPendingQuestion(""); setPendingError(""); setPlanning(false); clearPendingResearchPlan(); setParams({}, { replace: true }); };
  const chooseTemplate = (item: ResearchTemplate) => { setTemplate(item); setDraft(item.prompt); };
  const templates = discovery?.templates ?? [];
  const showSuggestions = !turns.length && !pendingQuestion && !draft.trim();
  const hasConversation = turns.length > 0 || Boolean(pendingQuestion);
  const composer = <div data-testid="analysis-composer" className="mx-auto w-full max-w-[760px] px-5 sm:px-7">
    {showSuggestions && templates.length > 0 && <div className="mb-3 flex gap-2 overflow-x-auto pb-1">{templates.map(item => <button key={item.id} type="button" onClick={() => chooseTemplate(item)} className="shrink-0 rounded-full border border-zinc-200/90 bg-white px-3 py-[7px] text-[12px] font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-900">{item.label}</button>)}</div>}
    <form onSubmit={submit} className="rounded-[22px] border border-zinc-300/90 bg-white p-1.5 transition-[border-color,box-shadow] focus-within:border-zinc-400 focus-within:shadow-[0_0_0_3px_rgba(24,24,27,.05)]"><div className="flex items-end gap-1.5"><span className="mb-1 ml-1 grid h-8 w-8 place-items-center rounded-full text-zinc-500"><Plus className="h-[18px] w-[18px] stroke-[1.8]" /></span><textarea aria-label="研究问题" rows={1} value={draft} onChange={event => { setDraft(event.target.value); setTemplate(null); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder={turns.length ? "继续追问" : "给 AI 发现发送消息"} className="max-h-32 min-h-[38px] flex-1 resize-none bg-transparent px-1 py-[7px] text-[13px] leading-6 text-zinc-900 outline-none placeholder:text-zinc-400" /><button type="submit" aria-label="发送消息" disabled={busy || !draft.trim()} className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-zinc-950 text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-400">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4 stroke-[2]" />}</button></div></form><p className="pt-1.5 text-center text-[10px] leading-4 text-zinc-400">AI 分析仅供研究参考，不构成投资建议</p>
  </div>;

  return <AIAnalysisShell recentTasks={recentTasks} activeTaskId={turns[turns.length - 1]?.task.id ?? conversationId} onNewAnalysis={resetConversation}>
    <div data-testid="ai-analysis-body" className="relative flex min-h-0 flex-1 flex-col">
      <div data-testid="active-conversation-scroll" className="min-h-0 flex-1 overflow-y-auto pb-28"><div className={hasConversation ? "" : "flex min-h-full flex-col"}><div className={hasConversation ? "" : "min-h-0 flex-1"}><AIAnalysisTimeline turns={turns} pendingQuestion={pendingQuestion} planning={planning} pendingError={pendingError} loadError={loadError} onRetry={task => void startAnalysis(task.question, task.template_id)} /></div></div></div>
      <div data-testid="composer-dock" className="absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-white via-white via-75% to-transparent pb-3 pt-6">{composer}</div>
    </div>
  </AIAnalysisShell>;
}
