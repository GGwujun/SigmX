import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, BarChart3, Bot, Database, LoaderCircle, Search, Sparkles, Wrench } from "lucide-react";
import { ResearchPlanPanel } from "@/components/public/ResearchPlanPanel";
import { ResearchProgress } from "@/components/public/ResearchProgress";
import { createResearchPlan, createResearchTask, getDiscovery, getResearchResult, listResearchEvents, listResearchTasks, waitForResearchTask, type PublicDiscovery, type ResearchPlan, type ResearchResult, type ResearchTask, type ResearchTemplate } from "@/lib/researchApi";
import { clearPendingResearchPlan, loadPendingResearchPlan, savePendingResearchPlan } from "@/lib/pendingResearchPlan";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

type RunState = "idle" | "planning" | "plan" | "running" | "done" | "error";

export function LandingPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [discovery, setDiscovery] = useState<PublicDiscovery | null>(null);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [template, setTemplate] = useState<ResearchTemplate | null>(null);
  const [phase, setPhase] = useState<RunState>("idle");
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [runError, setRunError] = useState("");
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
  const [activeTask, setActiveTask] = useState<ResearchTask | null>(null);
  const [agentEvents, setAgentEvents] = useState<Array<{ id: number; type: string; payload: Record<string, unknown> }>>([]);

  useEffect(() => {
    trackPersonalFunnel("landing_view");
    getDiscovery().then(setDiscovery).catch((error: Error) => setLoadError(error.message));
    if (isAuthenticated()) listResearchTasks(5).then(setRecentTasks).catch(() => undefined);
    const pending = loadPendingResearchPlan();
    if (pending && isAuthenticated()) {
      setQuery(pending.question);
      setPlan(pending.plan);
      setPhase("plan");
    }
  }, []);

  const dateLabel = discovery?.as_of ? `数据日期 ${discovery.as_of}` : "等待数据同步";
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
      setActiveTask(task);
      clearPendingResearchPlan();
      await waitForResearchTask(task, current => { setActiveTask(current); void listResearchEvents(task.id).then(setAgentEvents).catch(() => undefined); });
      setAgentEvents(await listResearchEvents(task.id).catch(() => []));
      const completed = await getResearchResult(task.id);
      setResult(completed); setPhase("done");
    } catch (error) {
      const message = error instanceof Error ? error.message : "研究运行失败";
      if (message === "登录已过期，请重新登录") {
        savePendingResearchPlan({ question: plan.question, templateId: plan.template_id, plan });
        navigate(`/login?next=${encodeURIComponent("/")}`);
        return;
      }
      setRunError(message); setPhase("error");
    }
  };

  return <div className="min-h-screen bg-slate-50 text-slate-950">
    <section className="border-b border-slate-200 bg-white"><div className="mx-auto max-w-[1440px] px-6 py-6">
      <div className="flex items-end justify-between gap-4"><div><div className="flex items-center gap-2 text-xs font-semibold text-primary"><BarChart3 className="h-4 w-4"/> AI DISCOVERY</div><h1 className="mt-1 text-2xl font-bold">AI 发现</h1><p className="mt-1 text-sm text-slate-500">让投研智能体调用 Data Hub 与 Skills，完成可追溯研究</p></div><div className="text-xs text-slate-500">{dateLabel} · {discovery?.is_delayed ? "延迟数据" : "最新数据"}</div></div>
      {loadError ? <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">市场数据加载失败：{loadError}</div> :
      <div className="mt-5 grid overflow-hidden rounded-lg border border-slate-200 bg-slate-50 sm:grid-cols-5">{discovery ? discovery.metrics.map(metric => <Metric key={metric.key} metric={metric}/>) : <div className="col-span-5 flex items-center gap-2 p-5 text-sm text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin"/> 正在读取市场数据</div>}</div>}
    </div></section>

    <main className="mx-auto max-w-[1440px] px-6 py-6">
      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><div className="flex items-center gap-3"><Search className="ml-2 h-5 w-5 text-primary"/><input aria-label="研究问题" value={query} onChange={e => { setQuery(e.target.value); setTemplate(null); setPlan(null); setResult(null); setPhase("idle"); }} placeholder="输入股票、行业或研究问题" className="h-11 flex-1 bg-transparent text-sm outline-none"/><button disabled={phase === "planning" || !query.trim()} className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50">{phase === "planning" ? "正在解析" : "生成研究计划"} {phase === "planning" ? <LoaderCircle className="h-4 w-4 animate-spin"/> : <ArrowRight className="h-4 w-4"/>}</button></div><div className="border-t border-slate-100 px-2 pt-2 text-xs text-slate-500">研究范围：A 股 · 非 ST {template ? `· 已采用“${template.label}”研究起点` : "· 自定义问题"}</div></form>
      <div className="mt-5 grid gap-5 md:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="space-y-4"><section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><div className="px-2 py-2"><h2 className="text-sm font-semibold">研究起点</h2><p className="mt-1 text-xs text-slate-400">选择后生成完整问题，可继续编辑</p></div><div className="space-y-1">{discovery?.templates.map(item => <button key={item.id} type="button" aria-pressed={template?.id === item.id} onClick={() => chooseTemplate(item)} className={`w-full rounded-lg px-3 py-3 text-left ${template?.id === item.id ? "bg-primary/10 text-primary" : "hover:bg-slate-50"}`}><div className="text-sm font-medium">{item.label}</div><div className="mt-1 text-xs opacity-70">{item.description}</div></button>)}</div><Link to="/product/data-hub" className="mt-4 flex items-center gap-1 border-t px-2 pt-4 text-xs font-semibold text-primary"><Database className="h-3.5 w-3.5"/> 查看数据能力</Link></section>{recentTasks.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><h2 className="px-2 py-2 text-sm font-semibold">最近研究</h2><div className="space-y-1">{recentTasks.filter(item => item.status === "succeeded").map(item => <Link key={item.id} to={`/research/result/${item.id}`} className="block rounded-lg px-3 py-2 text-xs leading-5 text-slate-600 hover:bg-slate-50 hover:text-primary">{item.question}</Link>)}</div></section>}</aside>
        <AgentWorkspace phase={phase} plan={plan} task={activeTask} events={agentEvents}>{result ? <ResultPanel result={result}/> : plan && phase === "plan" ? <ResearchPlanPanel plan={plan} onUseSuggested={(question) => { setTemplate(null); void buildPlan(question, null); }} onRun={run} onClose={() => { setPlan(null); setPhase("idle"); clearPendingResearchPlan(); }}/> : phase === "running" || phase === "error" ? <ResearchProgress question={query} steps={activeTask?.steps ?? plan?.steps ?? []} status={phase === "running" ? "running" : "error"} error={runError} onRetry={plan?.executable ? run : () => void buildPlan()} onEdit={() => setPhase(plan ? "plan" : "idle")}/> : <EmptyResearchState/>}</AgentWorkspace>
      </div>
    </main>
  </div>;
}

function AgentWorkspace({ phase, plan, task, events, children }: { phase: RunState; plan: ResearchPlan | null; task: ResearchTask | null; events: Array<{ id: number; type: string; payload: Record<string, unknown> }>; children: ReactNode }) {
  const status = phase === "running" ? "执行中" : phase === "done" ? "已完成" : phase === "error" ? "需要处理" : phase === "plan" ? "等待确认计划" : "待命";
  return <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><header className="flex flex-wrap items-center justify-between gap-3 border-b bg-slate-950 px-5 py-4 text-white"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary"><Bot className="h-5 w-5"/></span><div><h2 className="font-semibold">AI 投研智能体</h2><p className="mt-0.5 text-xs text-slate-400">通用研究 Agent · 只读研究模式</p></div></div><div className="flex flex-wrap gap-2 text-[11px]"><span className="rounded-full bg-white/10 px-3 py-1.5"><Wrench className="mr-1 inline h-3 w-3"/>Data Hub 工具</span><span className="rounded-full bg-white/10 px-3 py-1.5"><Sparkles className="mr-1 inline h-3 w-3"/>自动匹配 Skills</span><span className={`rounded-full px-3 py-1.5 ${phase === "running" ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10"}`}>{status}</span></div></header>{plan && <div className="flex flex-wrap gap-2 border-b bg-slate-50 px-5 py-3 text-xs text-slate-500"><span>执行方式：{plan.execution_mode === "agent" ? "AI Agent" : "规则降级"}</span>{plan.model && <span>· 模型：{plan.model}</span>}<span>· 数据集：{plan.datasets.filter(item => item.status !== "unavailable").length}</span><span>· Skills：{plan.skills?.length ? plan.skills.join("、") : "运行时自动选择"}</span>{task && <span>· 任务：{task.id.slice(0, 8)}</span>}</div>}{events.length > 0 && <div className="flex gap-2 overflow-x-auto border-b px-5 py-3 text-xs">{events.map(event => <span key={event.id} className="whitespace-nowrap rounded-full border bg-white px-3 py-1.5 text-slate-600">{eventLabel(event.type, event.payload)}</span>)}</div>}<div className="[&>section]:rounded-none [&>section]:border-0 [&>section]:shadow-none">{children}</div></section>;
}

function eventLabel(type: string, payload: Record<string, unknown>) { if (type === "tool_started") return `调用 ${String(payload.tool ?? "研究工具")}`; if (type === "tool_completed") return `${String(payload.tool ?? "研究工具")} 返回证据`; if (type === "completed") return "研究完成"; if (type === "running") return "正在检索与核验"; return String(payload.message ?? type); }

function Metric({ metric }: { metric: PublicDiscovery["metrics"][number] }) {
  const unavailable = metric.quality === "unavailable" || metric.value == null;
  const formatNumber = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  const value = unavailable
    ? "暂无数据"
    : metric.secondary_value == null
      ? `${formatNumber(metric.value!)}${metric.unit ?? ""}`
      : `${formatNumber(metric.value!)} / ${formatNumber(metric.secondary_value)}${metric.unit ? ` ${metric.unit}` : ""}`;
  const change = unavailable || metric.change == null ? null : `${metric.change > 0 ? "+" : ""}${metric.change.toFixed(2)}%`;
  return <div className="border-r border-slate-200 px-4 py-3"><div className="text-xs text-slate-500">{metric.label}</div><div className="mt-1 flex items-baseline gap-2"><span className="font-semibold tabular-nums">{value}</span>{change && <span className={metric.change! < 0 ? "text-xs text-red-500" : "text-xs text-success"}>{change}</span>}</div></div>;
}

function ResultPanel({ result }: { result: ResearchResult }) {
  return <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b p-5"><h2 className="font-semibold">研究结果</h2><p className="mt-2 text-sm text-slate-600">{result.summary}</p><div className="mt-2 text-xs text-slate-400">数据日期 {result.as_of ?? "未知"} · {result.source}</div></div><div className="divide-y">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} className="flex items-start justify-between gap-4 p-5 hover:bg-slate-50"><div><div className="font-semibold">{item.name} <span className="font-mono text-xs text-slate-400">{item.code}</span></div><p className="mt-2 text-xs text-slate-500">{item.reason}</p></div><div className="shrink-0 text-right text-xs text-slate-500"><div>PE {item.pe_ttm ?? "—"}</div><div>股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</div></div></Link>)}</div><div className="flex justify-end border-t bg-slate-50 p-4"><Link to={`/research/result/${result.task_id}`} className="font-semibold text-primary">查看完整结果</Link></div></section>;
}

function EmptyResearchState() {
  const abilities = ["估值与分红", "市值筛选", "现金流识别", "行业基准预检", "历史分位预检"];
  return <section className="min-h-[430px] rounded-xl border border-slate-200 bg-white p-8 shadow-sm"><div className="mx-auto max-w-2xl py-8 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-5 w-5"/></span><h2 className="mt-4 text-lg font-semibold">先生成计划，再运行研究</h2><p className="mt-2 text-sm leading-6 text-slate-500">系统会先拆解指标、时间范围和比较基准，并在运行前告诉你哪些条件可以可靠执行。</p><div className="mt-6 flex flex-wrap justify-center gap-2">{abilities.map(item => <span key={item} className="rounded-full border bg-slate-50 px-3 py-1.5 text-xs text-slate-600">{item}</span>)}</div><div className="mt-8 rounded-lg bg-slate-50 p-4 text-left text-xs leading-6 text-slate-500"><span className="font-semibold text-slate-700">可以这样问：</span> 寻找市盈率不高于 20 倍、股息率不低于 3% 的 A 股公司，并按市值从小到大排序。</div></div></section>;
}
