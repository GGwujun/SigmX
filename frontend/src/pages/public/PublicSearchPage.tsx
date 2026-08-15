import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bookmark, Monitor } from "lucide-react";

import { cloudResearchApi, type PublicSearchResult } from "@/lib/cloudResearchApi";
import { isAuthenticated } from "@/lib/apiAuth";

export function PublicSearchPage() {
  const { id = "" } = useParams();
  const query = decodeURIComponent(id);
  const navigate = useNavigate();
  const [result, setResult] = useState<PublicSearchResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void cloudResearchApi.search(query).then(setResult).catch((reason) => setError(reason instanceof Error ? reason.message : "查询失败"));
  }, [query]);

  const save = async () => {
    const summary = { matches: result?.items.length ?? 0, interpretation: result?.interpretation ?? [] };
    if (!isAuthenticated()) {
      window.sessionStorage.setItem("sigmx_pending_saved_query", JSON.stringify({ query, result_summary: summary }));
      navigate(`/login?next=${encodeURIComponent(`/query/${encodeURIComponent(query)}`)}`);
      return;
    }
    await cloudResearchApi.saveQuery(query, summary);
  };

  return <div className="mx-auto max-w-5xl space-y-6 px-4 py-12">
    <header><p className="text-xs font-medium uppercase tracking-widest text-primary">AI 选股 · 轻量验证</p><h1 className="mt-2 text-3xl font-bold">{query}</h1><p className="mt-2 text-sm text-muted-foreground">匿名用户可查看有限真实结果；完整保存和持续研究需要登录。</p></header>
    {error && <div role="alert" className="rounded-lg border border-destructive/40 p-4 text-destructive">{error}</div>}
    {!result && !error && <p className="text-sm text-muted-foreground">正在查询…</p>}
    {result && <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/20 p-4"><div><div className="text-sm">{result.interpretation.length ? result.interpretation.join(" · ") : "代码、名称或行业匹配"}</div><div className="mt-1 text-xs text-muted-foreground">延迟数据 · 来源 {result.source}</div></div><button onClick={() => void save()} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"><Bookmark className="h-4 w-4" />保存查询</button></div>
      <div className="space-y-3">{result.items.length === 0 && <p className="rounded-lg border p-6 text-sm text-muted-foreground">当前数据中没有匹配结果，请调整条件。</p>}{result.items.map((item) => <Link key={item.code} to={`/stock/${item.code}`} className="block rounded-xl border bg-card p-5 hover:border-primary/40"><div className="flex justify-between"><div><strong>{item.name}</strong><code className="ml-2 text-xs text-muted-foreground">{item.code}</code></div><span>{item.close?.toLocaleString() ?? "—"}</span></div><div className="mt-3 grid grid-cols-3 gap-2 text-xs text-muted-foreground"><span>PE {item.pe_ttm ?? "—"}</span><span>PB {item.pb ?? "—"}</span><span>股息率 {item.dividend_yield ?? "—"}%</span></div></Link>)}</div>
      <Link to="/download" className="inline-flex items-center gap-2 text-sm font-medium text-primary"><Monitor className="h-4 w-4" />在 Desktop 中继续深度研究</Link>
    </>}
  </div>;
}
