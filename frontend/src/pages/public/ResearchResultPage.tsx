import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Database, LoaderCircle, RotateCcw } from "lucide-react";
import { getResearchResult, type ResearchResult } from "@/lib/researchApi";

export function ResearchResultPage() {
  const { taskId = "" } = useParams();
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getResearchResult(taskId).then(setResult).catch((cause: Error) => setError(cause.message)); }, [taskId]);
  if (error) return <State title="研究结果无法读取" detail={error}/>;
  if (!result) return <State title="正在读取研究结果" detail="从服务端加载已保存的候选与证据" loading/>;
  return <div className="min-h-screen bg-slate-50 text-slate-950"><header className="border-b bg-white"><div className="mx-auto max-w-6xl px-6 py-7"><Link to="/" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500"><ArrowLeft className="h-3.5 w-3.5"/>返回 AI 发现</Link><div className="mt-5 flex items-start justify-between gap-6"><div><h1 className="text-3xl font-bold">{result.question}</h1><div className="mt-3 flex gap-3 text-xs text-slate-500"><span>数据日期 {result.as_of ?? "未知"}</span><span>来源 {result.source}</span><span>任务 {result.task_id}</span></div></div><Link to={`/?q=${encodeURIComponent(result.question)}`} className="inline-flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold hover:bg-slate-50"><RotateCcw className="h-4 w-4"/>使用该问题再次研究</Link></div></div></header><main className="mx-auto max-w-6xl space-y-5 px-6 py-7"><section className="rounded-xl border border-primary/20 bg-white p-6"><h2 className="text-lg font-bold">研究结论</h2><p className="mt-3 text-sm leading-7 text-slate-600">{result.summary}</p><div className="mt-4 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-slate-100 px-3 py-1.5">范围：{String(result.scope.market ?? "A股")}</span>{result.scope.exclude_st === true && <span className="rounded-full bg-slate-100 px-3 py-1.5">已排除 ST</span>}</div></section><section className="overflow-hidden rounded-xl border bg-white"><div className="border-b p-5"><h2 className="font-bold">候选与证据</h2><p className="mt-1 text-xs text-slate-500">共 {result.candidates.length} 个候选；每项证据均展示口径、来源与数据日期</p></div><div className="divide-y">{result.candidates.map(item => <article key={item.code} className="p-5"><div className="flex justify-between"><Link to={`/stock/${item.code}`} className="font-semibold hover:text-primary">{item.name} · {item.code}</Link><span className="text-xs text-slate-500">{item.industry ?? "行业未知"}</span></div><p className="mt-3 text-sm text-slate-600">{item.reason}</p><div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">{item.evidence.map((evidence, index) => <div key={`${evidence.field}-${index}`} className="rounded-lg bg-slate-50 p-3 text-xs"><div className="text-slate-400">{evidenceLabel(evidence.field)}</div><div className="mt-1 font-semibold">{formatEvidence(evidence.field, evidence.value)}</div><div className="mt-2 text-[11px] leading-4 text-slate-400"><div>{evidence.as_of ?? "日期未知"}</div><div>来源：{evidence.source}</div></div></div>)}</div></article>)}</div></section><section className="grid gap-4 md:grid-cols-2"><div className="rounded-xl border bg-white p-5"><h2 className="flex items-center gap-2 font-bold"><Database className="h-4 w-4 text-primary"/>数据说明</h2><p className="mt-3 text-sm text-slate-600">本页展示服务端保存的研究快照；再次打开时不会用新数据覆盖原结果，便于复核。</p></div><div className="rounded-xl border border-amber-200 bg-amber-50 p-5"><h2 className="font-bold text-amber-900">风险提示</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-amber-900">{result.risks.map(risk => <li key={risk}>{risk}</li>)}</ul></div></section></main></div>;
}

const EVIDENCE_LABELS: Record<string, string> = { close: "收盘价", pe_ttm: "市盈率（TTM）", pb: "市净率", dividend_yield: "股息率（TTM）", total_market_value: "总市值" };
function evidenceLabel(field: string) { return EVIDENCE_LABELS[field] ?? field; }
function formatEvidence(field: string, value: unknown) {
  if (typeof value !== "number") return value == null ? "—" : String(value);
  if (field === "close") return `${value.toFixed(2)} 元`;
  if (field === "pe_ttm" || field === "pb") return `${value.toFixed(2)} 倍`;
  if (field === "dividend_yield") return `${value.toFixed(2)}%`;
  if (field === "total_market_value") return `${(value / 10_000).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亿元`;
  return value.toLocaleString("zh-CN");
}

function State({ title, detail, loading = false }: { title: string; detail: string; loading?: boolean }) { return <div className="grid min-h-[60vh] place-items-center bg-slate-50"><div className="text-center">{loading && <LoaderCircle className="mx-auto h-6 w-6 animate-spin text-primary"/>}<h1 className="mt-3 text-xl font-bold">{title}</h1><p className="mt-2 text-sm text-slate-500">{detail}</p><Link to="/" className="mt-5 inline-block text-sm font-semibold text-primary">返回 AI 发现</Link></div></div>; }
