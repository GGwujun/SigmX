import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bookmark, Monitor } from "lucide-react";
import { DataStatus, EmptyState, ErrorState, Panel } from "@sigmx/ui";

import { cloudResearchApi, type PublicSearchResult } from "@/lib/cloudResearchApi";
import { isAuthenticated } from "@/lib/apiAuth";
import { trackPersonalFunnel } from "@/lib/personalFunnel";
import { recordQueryExecution } from "@/lib/productApi";

export function PublicSearchPage() {
  const { id = "" } = useParams();
  const query = decodeURIComponent(id);
  const navigate = useNavigate();
  const [result, setResult] = useState<PublicSearchResult | null>(null);
  const [error, setError] = useState("");
  const executionKey = useRef(`web:${Date.now()}:${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    trackPersonalFunnel("search_submitted");
    void cloudResearchApi.search(query).then(setResult).catch((reason) => setError(reason instanceof Error ? reason.message : "查询失败"));
  }, [query]);

  useEffect(() => { if (result) trackPersonalFunnel("result_view"); }, [result]);

  useEffect(() => {
    if (!result || !isAuthenticated()) return;
    void recordQueryExecution({
      query,
      intent: result.intent ?? "instrument_search",
      conditions: result.interpretation.map(label => ({ label })),
      result_count: result.items.length,
      idempotency_key: executionKey.current,
    }).catch(() => undefined);
  }, [query, result]);

  const save = async () => {
    const summary = { matches: result?.items.length ?? 0, interpretation: result?.interpretation ?? [] };
    if (!isAuthenticated()) {
      window.sessionStorage.setItem("sigmx_pending_saved_query", JSON.stringify({ query, result_summary: summary }));
      navigate(`/login?next=${encodeURIComponent(`/query/${encodeURIComponent(query)}`)}`);
      return;
    }
    await cloudResearchApi.saveQuery(query, summary);
  };

  return <div className="mx-auto max-w-6xl space-y-5 px-4 py-8 sm:px-6">
    <header className="border-b pb-5"><p className="text-xs font-medium uppercase tracking-[.18em] text-primary">SigmX Discovery</p><h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{query}</h1><p className="mt-2 text-sm text-muted-foreground">解释查询意图，展示真实数据，并将结果沉淀为持续研究资产。</p></header>
    {error && <ErrorState title="查询失败" description={error} onRetry={() => window.location.reload()} />}
    {!result && !error && <div role="status" className="page-state"><strong>正在解析查询并读取数据…</strong></div>}
    {result && <>
      <Panel title="查询解释" description={result.intent ?? "instrument_search"} action={<button onClick={() => void save()} className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"><Bookmark className="h-3.5 w-3.5" />保存查询</button>}>
        <div className="flex flex-wrap gap-2">{(result.interpretation.length ? result.interpretation : ["代码、名称或行业匹配"]).map(item => <span key={item} className="rounded border bg-muted/30 px-2 py-1 text-xs">{item}</span>)}</div>
        {result.answer && <p className="mt-4 border-l-2 border-primary pl-3 text-sm leading-6">{result.answer}</p>}
        <DataStatus source={result.source} asOf={result.items.find(item => item.as_of)?.as_of ?? null} freshness={result.is_delayed ? "延迟数据" : "实时"} quality={result.answer?.includes("暂不可用") ? "degraded" : "verified"} />
      </Panel>
      {(result.resources?.length ?? 0) > 0 && <Panel title="相关文档" description="继续查看接口定义、认证与示例"><div className="grid gap-2 md:grid-cols-2">{result.resources!.map(resource => <Link key={resource.url} to={resource.url} className="rounded border p-3 hover:border-primary/50"><strong className="text-sm">{resource.title}</strong><p className="mt-1 text-xs text-muted-foreground">{resource.description}</p></Link>)}</div></Panel>}
      <Panel title="匹配结果" description={`${result.items.length} 个结果`}>
        {result.items.length === 0 && !result.answer && !(result.resources?.length) && <EmptyState title="没有匹配结果" description="调整关键词、筛选条件或直接输入证券代码。" />}
        <div className="divide-y">{result.items.map((item) => <Link aria-label={`${item.name} ${item.code}`} key={item.code} to={`/${item.instrument_type === "fund" ? "fund" : "stock"}/${item.code}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-2 py-3 hover:bg-muted/25"><div><strong className="text-sm">{item.name}</strong><code className="ml-2 text-xs text-muted-foreground">{item.code}</code><div className="mt-1 text-xs text-muted-foreground">{item.industry ?? item.instrument_type ?? "—"}</div></div><div className="text-right font-mono text-sm"><div>{item.close?.toLocaleString() ?? "—"}</div><div className="mt-1 text-[11px] text-muted-foreground">PE {item.pe_ttm ?? "—"} · PB {item.pb ?? "—"} · 股息 {item.dividend_yield ?? "—"}%</div></div></Link>)}</div>
      </Panel>
      <Link to="/download" className="inline-flex items-center gap-2 text-sm font-medium text-primary"><Monitor className="h-4 w-4" />在 Desktop 中继续深度研究</Link>
    </>}
  </div>;
}
