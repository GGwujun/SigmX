import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowUp, ChevronDown, LoaderCircle, Plus } from "lucide-react";
import { toast } from "sonner";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AIAnalysisShell } from "@/components/public/AIAnalysisShell";
import { AIAnalysisTimeline } from "@/components/public/AIAnalysisTimeline";
import { ChatTopActions } from "@/components/public/ChatTopActions";
import { OutputFilesPanel } from "@/components/public/OutputFilesPanel";
import { MarkdownDrawer } from "@/components/public/MarkdownDrawer";
import { buildDeepResearchPlan, cancelResearchTask, createResearchPlan, createResearchTask, followUpResearchTask, getDiscovery, getResearchResult, getResearchThread, listResearchEvents, listResearchTasks, streamResearchEvents, waitForResearchTask, type PublicDiscovery, type ResearchConversationTurn, type ResearchEvent, type ResearchPlan, type ResearchTask, type ResearchTemplate } from "@/lib/researchApi";
import { buildConversationFiles, buildConversationMarkdown, downloadTextFile, type ConversationFile } from "@/lib/conversationFiles";
import { clearPendingResearchPlan, loadPendingResearchPlan, savePendingResearchPlan } from "@/lib/pendingResearchPlan";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

export function LandingPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [discovery, setDiscovery] = useState<PublicDiscovery | null>(null);
  const [loadError, setLoadError] = useState("");
  // ?deep=<code>（个股页「深度研究」跳转）：预填代码并进入深研模式
  const [draft, setDraft] = useState(params.get("deep") ?? params.get("q") ?? "");
  const [deepMode, setDeepMode] = useState(Boolean(params.get("deep")));
  const [template, setTemplate] = useState<ResearchTemplate | null>(null);
  const [turns, setTurns] = useState<ResearchConversationTurn[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [planning, setPlanning] = useState(false);
  const [pendingError, setPendingError] = useState("");
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
  const restoredPending = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const conversationId = params.get("conversation");
  const busy = planning || turns.some(turn => ["queued", "running"].includes(turn.task.status));

  useEffect(() => {
    trackPersonalFunnel("landing_view");
    getDiscovery().then(setDiscovery).catch((error: Error) => setLoadError(error.message));
    if (isAuthenticated()) listResearchTasks(20).then(setRecentTasks).catch(() => undefined);
    if (params.get("deep")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 吸底自动滚动：流式输出时贴底跟随，用户上翻回看就不再抢滚动（学习 VR AiMessages）。
  // atBottom 只在布尔翻转时 setState（React 同值 bail-out），滚动事件不会引发重渲染。
  const [atBottom, setAtBottom] = useState(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const next = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
      stickToBottom.current = next;
      setAtBottom(prev => (prev === next ? prev : next));
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    const el = scrollRef.current;
    // scrollTop 赋值而非 scrollTo()：流式高频滚动要的就是即时贴底，且测试环境（jsdom）没有 scrollTo。
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [turns, pendingQuestion]);
  // 输入框按内容自动撑高（封顶 max-h-32 后转内部滚动），draft 被程序清空时同步复位。
  useEffect(() => {
    const el = draftRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [draft]);

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

  // 深研模式：本地构造六阶段管线计划（不走 /api/research/plans 的 LLM 规划），
  // 后端按 plan.pipeline + plan.code 分流到 PipelineDispatchRunner。
  const startDeepResearch = (question: string) => {
    const code = /\b\d{6}\b/.exec(question)?.[0];
    if (!code) {
      setPendingQuestion(question); setPlanning(false);
      setPendingError("深度研究需要 6 位股票代码，例如 600519。");
      return;
    }
    setDraft(""); setPendingQuestion(question); setPlanning(true); setPendingError("");
    void executePlan(buildDeepResearchPlan(code, question));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    if (deepMode) { startDeepResearch(question); return; }
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

  const resetConversation = () => { setDraft(""); setDeepMode(false); setTemplate(null); setTurns([]); setPendingQuestion(""); setPendingError(""); setPlanning(false); setPanelOpen(false); setPreviewFile(null); clearPendingResearchPlan(); setParams({}, { replace: true }); };
  const chooseTemplate = (item: ResearchTemplate) => { setDeepMode(false); setTemplate(item); setDraft(item.prompt); };
  const activateDeepResearch = () => { setDeepMode(true); setTemplate(null); setDraft(""); };
  const templates = discovery?.templates ?? [];
  const showSuggestions = !turns.length && !pendingQuestion && !draft.trim();
  const hasConversation = turns.length > 0 || Boolean(pendingQuestion);

  // 右上角操作区与「输出」面板：文件由真实研究结果派生；分享锚定最后一个 turn。
  const [panelOpen, setPanelOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<ConversationFile | null>(null);
  const files = useMemo(() => buildConversationFiles(turns), [turns]);
  const mdFiles = useMemo(() => files.filter(file => file.kind === "md"), [files]);
  const runningTaskId = turns.find(turn => ["queued", "running"].includes(turn.task.status))?.task.id ?? null;
  const lastTurn = turns[turns.length - 1];
  const conversationUrl = conversationId ? `${window.location.origin}/?conversation=${encodeURIComponent(conversationId)}` : null;
  const cancelRunning = async () => {
    if (!runningTaskId) return;
    try {
      const task = await cancelResearchTask(runningTaskId);
      updateTurn(task.id, turn => ({ ...turn, task }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "取消失败，请稍后再试");
    }
  };
  const exportConversation = () => {
    const date = new Date().toISOString().slice(0, 10);
    downloadTextFile(`SigmX-对话导出-${date}.md`, buildConversationMarkdown(turns), "text/markdown;charset=utf-8");
  };
  const composer = <div data-testid="analysis-composer" className="mx-auto w-full max-w-[760px] px-5 sm:px-7">
    {/* 截图 composer 微细节：~26px 圆角接近半高、1px #e5e5e5 描边、阴影极淡；
        ＋钮透明无底、发送钮 36px 圆（禁用态浅灰底+中灰箭头）、输入文字 15px。 */}
    <form onSubmit={submit} className="rounded-[26px] border border-[#e5e5e5] bg-white p-2 shadow-[0_4px_16px_rgba(0,0,0,.04)] transition-[border-color,box-shadow] focus-within:border-[#c9c9c9] focus-within:shadow-[0_6px_22px_rgba(0,0,0,.07)]"><div className="flex items-end gap-1.5"><button type="button" aria-label="展开更多" className="mb-1 ml-1 grid h-9 w-9 place-items-center rounded-full text-[#4d4d4d] transition-colors hover:bg-[#f0f0f0]"><Plus className="h-[18px] w-[18px] stroke-[1.8]" /></button><textarea ref={draftRef} aria-label="研究问题" rows={1} value={draft} onChange={event => { setDraft(event.target.value); setTemplate(null); }} onKeyDown={event => { // 中文输入法选字期间的 Enter 是确认候选词，不是发送（isComposing 只在原生事件上）。
      if (event.nativeEvent.isComposing) return;
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
    }} placeholder={deepMode ? "输入 6 位股票代码，如 600519" : turns.length ? "继续追问" : "给 AI 发现发送消息"} className="max-h-32 min-h-[38px] flex-1 resize-none overflow-y-auto bg-transparent px-1 py-[7px] text-[15px] leading-6 text-[#0d0d0d] outline-none placeholder:text-[#9b9b9b]" /><button type="submit" aria-label="发送消息" disabled={busy || !draft.trim()} className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0d0d0d] text-white transition-colors hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:bg-[#e5e5e5] disabled:text-[#9b9b9b]">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4 stroke-[2.2]" />}</button></div></form>
    {/* 建议 chips 放输入框下方（学习 ChatGPT：输入为主、建议为辅），开始输入即隐藏 */}
    {showSuggestions && <div className="mt-3 flex justify-center gap-2 overflow-x-auto pb-1">{templates.map(item => <button key={item.id} type="button" onClick={() => chooseTemplate(item)} className="shrink-0 rounded-full border border-[#e5e5e5] bg-white px-4 py-2 text-[12.5px] font-medium text-[#4d4d4d] transition-colors hover:bg-[#f7f7f7]">{item.label}</button>)}<button type="button" aria-pressed={deepMode} onClick={activateDeepResearch} className={deepMode ? "shrink-0 rounded-full border border-[#0d0d0d] bg-[#0d0d0d] px-4 py-2 text-[12.5px] font-semibold text-white" : "shrink-0 rounded-full border border-[#e5e5e5] bg-white px-4 py-2 text-[12.5px] font-medium text-[#4d4d4d] transition-colors hover:bg-[#f7f7f7]"}>个股深度研究</button></div>}
    <p className="pt-2.5 text-center text-[10.5px] leading-4 text-[#8f8f8f]">AI 分析仅供研究参考，不构成投资建议</p>
  </div>;

  return <AIAnalysisShell recentTasks={recentTasks} activeTaskId={turns[turns.length - 1]?.task.id ?? conversationId} onNewAnalysis={resetConversation}>
    <div data-testid="ai-analysis-body" className="relative flex min-h-0 flex-1 flex-col">
      {hasConversation && <ChatTopActions busy={busy} shareTaskId={lastTurn?.task.id ?? null} runningTaskId={runningTaskId} conversationUrl={conversationUrl} panelOpen={panelOpen} onTogglePanel={() => setPanelOpen(value => !value)} onNewAnalysis={resetConversation} onCancel={() => void cancelRunning()} onExportMarkdown={exportConversation} />}
      {panelOpen && <OutputFilesPanel files={files} onPreview={setPreviewFile} />}
      {previewFile && <MarkdownDrawer file={previewFile} mdFiles={mdFiles} onSwitch={setPreviewFile} onClose={() => setPreviewFile(null)} />}
      <div data-testid="active-conversation-scroll" ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto pb-32"><div className={hasConversation ? "" : "flex min-h-full flex-col"}><div className={hasConversation ? "" : "flex min-h-0 flex-1 flex-col"}><AIAnalysisTimeline turns={turns} pendingQuestion={pendingQuestion} planning={planning} pendingError={pendingError} loadError={loadError} onRetry={task => void startAnalysis(task.question, task.template_id)} /></div></div></div>
      {/* 对话中上翻后浮现的居中回底圆钮（对齐 ChatGPT 截图细节） */}
      {hasConversation && !atBottom && <button type="button" aria-label="回到底部" onClick={() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; stickToBottom.current = true; setAtBottom(true); }} className="absolute bottom-[128px] left-1/2 z-20 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-black/10 bg-white text-[#4d4d4d] shadow-[0_4px_16px_rgba(0,0,0,.12)] transition-colors hover:bg-[#f7f7f7]"><ChevronDown className="h-4 w-4 stroke-[2]" /></button>}
      <div data-testid="composer-dock" className="absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-white via-white via-75% to-transparent pb-3 pt-6">{composer}</div>
    </div>
  </AIAnalysisShell>;
}
