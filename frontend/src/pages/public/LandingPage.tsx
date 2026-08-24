import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, BarChart3, Database, LoaderCircle, Search, Sparkles, X } from "lucide-react";
import { createResearchTask, getDiscovery, getResearchResult, type PublicDiscovery, type ResearchResult, type ResearchTemplate } from "@/lib/researchApi";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

type RunState = "idle" | "plan" | "running" | "done" | "error";

export function LandingPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [discovery, setDiscovery] = useState<PublicDiscovery | null>(null);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [template, setTemplate] = useState<ResearchTemplate | null>(null);
  const [phase, setPhase] = useState<RunState>("idle");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [runError, setRunError] = useState("");

  useEffect(() => {
    trackPersonalFunnel("landing_view");
    getDiscovery().then(setDiscovery).catch((error: Error) => setLoadError(error.message));
  }, []);

  const dateLabel = discovery?.as_of ? `数据日期 ${discovery.as_of}` : "等待数据同步";
  const chooseTemplate = (item: ResearchTemplate) => { setTemplate(item); setQuery(item.prompt); setResult(null); setPhase("idle"); };
  const submit = (event: FormEvent) => { event.preventDefault(); if (query.trim()) setPhase("plan"); };
  const run = async () => {
    if (!isAuthenticated()) { navigate(`/login?next=${encodeURIComponent("/")}`); return; }
    setPhase("running"); setRunError("");
    try {
      const task = await createResearchTask({ question: query.trim(), template_id: template?.id ?? null, scope: { market: "A股", exclude_st: true }, constraints: [] });
      const completed = await getResearchResult(task.id);
      setResult(completed); setPhase("done");
    } catch (error) { setRunError(error instanceof Error ? error.message : "研究运行失败"); setPhase("error"); }
  };

  return <div className="min-h-screen bg-slate-50 text-slate-950">
    <section className="border-b border-slate-200 bg-white"><div className="mx-auto max-w-[1440px] px-6 py-6">
      <div className="flex items-end justify-between gap-4"><div><div className="flex items-center gap-2 text-xs font-semibold text-primary"><BarChart3 className="h-4 w-4"/> WEB RESEARCH</div><h1 className="mt-1 text-2xl font-bold">市场发现</h1><p className="mt-1 text-sm text-slate-500">从真实市场数据开始，把问题转成可追溯的研究结果</p></div><div className="text-xs text-slate-500">{dateLabel} · {discovery?.is_delayed ? "延迟数据" : "最新数据"}</div></div>
      {loadError ? <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">市场数据加载失败：{loadError}</div> :
      <div className="mt-5 grid overflow-hidden rounded-lg border border-slate-200 bg-slate-50 sm:grid-cols-5">{discovery ? discovery.metrics.map(metric => <Metric key={metric.key} metric={metric}/>) : <div className="col-span-5 flex items-center gap-2 p-5 text-sm text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin"/> 正在读取市场数据</div>}</div>}
    </div></section>

    <main className="mx-auto max-w-[1440px] px-6 py-6">
      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><div className="flex items-center gap-3"><Search className="ml-2 h-5 w-5 text-primary"/><input aria-label="研究问题" value={query} onChange={e => { setQuery(e.target.value); setTemplate(null); setResult(null); }} placeholder="输入股票、行业或研究问题" className="h-11 flex-1 bg-transparent text-sm outline-none"/><button className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground">运行研究 <ArrowRight className="h-4 w-4"/></button></div><div className="border-t border-slate-100 px-2 pt-2 text-xs text-slate-500">研究范围：A 股 · 非 ST {template ? `· 已采用“${template.label}”模板` : "· 自定义问题"}</div></form>
      <div className="mt-5 grid gap-5 md:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"><div className="px-2 py-2"><h2 className="text-sm font-semibold">研究模板</h2><p className="mt-1 text-xs text-slate-400">选择后会生成可继续编辑的研究问题</p></div><div className="space-y-1">{discovery?.templates.map(item => <button key={item.id} type="button" aria-pressed={template?.id === item.id} onClick={() => chooseTemplate(item)} className={`w-full rounded-lg px-3 py-3 text-left ${template?.id === item.id ? "bg-primary/10 text-primary" : "hover:bg-slate-50"}`}><div className="text-sm font-medium">{item.label}</div><div className="mt-1 text-xs opacity-70">{item.description}</div></button>)}</div><Link to="/product/data-hub" className="mt-4 flex items-center gap-1 border-t px-2 pt-4 text-xs font-semibold text-primary"><Database className="h-3.5 w-3.5"/> 查看数据能力</Link></aside>
        {!result ? <section className="grid min-h-[430px] place-items-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center"><div className="max-w-md"><span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-5 w-5"/></span><h2 className="mt-4 text-lg font-semibold">从一个研究问题开始</h2><p className="mt-2 text-sm leading-6 text-slate-500">选择模板或直接提问。提交后由服务端读取已入库数据、执行筛选并保存结果与证据。</p></div></section> : <ResultPanel result={result}/>} 
      </div>
    </main>
    {phase !== "idle" && phase !== "done" && <RunDialog phase={phase} question={query} error={runError} onRun={run} onClose={() => setPhase("idle")}/>} 
  </div>;
}

function Metric({ metric }: { metric: PublicDiscovery["metrics"][number] }) {
  const value = metric.quality !== "available" || metric.value == null ? "暂无数据" : `${metric.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${metric.unit ?? ""}`;
  const change = metric.change == null ? null : `${metric.change > 0 ? "+" : ""}${metric.change.toFixed(2)}%`;
  return <div className="border-r border-slate-200 px-4 py-3"><div className="text-xs text-slate-500">{metric.label}</div><div className="mt-1 flex items-baseline gap-2"><span className="font-semibold tabular-nums">{value}</span>{change && <span className={metric.change! < 0 ? "text-xs text-red-500" : "text-xs text-success"}>{change}</span>}</div></div>;
}

function ResultPanel({ result }: { result: ResearchResult }) {
  return <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b p-5"><h2 className="font-semibold">研究结果</h2><p className="mt-2 text-sm text-slate-600">{result.summary}</p><div className="mt-2 text-xs text-slate-400">数据日期 {result.as_of ?? "未知"} · {result.source}</div></div><div className="divide-y">{result.candidates.map(item => <Link key={item.code} to={`/stock/${item.code}`} className="flex items-start justify-between gap-4 p-5 hover:bg-slate-50"><div><div className="font-semibold">{item.name} <span className="font-mono text-xs text-slate-400">{item.code}</span></div><p className="mt-2 text-xs text-slate-500">{item.reason}</p></div><div className="shrink-0 text-right text-xs text-slate-500"><div>PE {item.pe_ttm ?? "—"}</div><div>股息率 {item.dividend_yield == null ? "—" : `${item.dividend_yield}%`}</div></div></Link>)}</div><div className="flex justify-end border-t bg-slate-50 p-4"><Link to={`/research/result/${result.task_id}`} className="font-semibold text-primary">查看完整结果</Link></div></section>;
}

function RunDialog({ phase, question, error, onRun, onClose }: { phase: RunState; question: string; error: string; onRun: () => void; onClose: () => void }) {
  return <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4"><section role="dialog" aria-label="研究流程" className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl"><div className="flex justify-between"><div><h2 className="text-xl font-bold">{phase === "plan" ? "研究计划" : phase === "running" ? "正在执行研究" : "研究运行失败"}</h2><p className="mt-2 text-sm text-slate-500">{question}</p></div><button aria-label="关闭" onClick={onClose}><X className="h-5 w-5"/></button></div>{phase === "plan" && <><ol className="mt-6 grid gap-3 text-sm"><li>1. 解析自然语言问题与研究范围</li><li>2. 查询行情、估值和分红等已入库数据</li><li>3. 保存候选、证据来源及数据日期</li></ol><button onClick={onRun} className="mt-6 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">开始执行</button></>}{phase === "running" && <div className="mt-8 flex items-center gap-3 text-sm text-slate-600"><LoaderCircle className="h-5 w-5 animate-spin text-primary"/> 服务端正在执行并持久化研究结果</div>}{phase === "error" && <div className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>}</section></div>;
}
