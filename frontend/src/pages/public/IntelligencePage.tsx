import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Database, ExternalLink, LoaderCircle, Newspaper, Search, Sparkles, X } from "lucide-react";

interface Article { title: string; url: string; source: string; published: string; snippet: string }
interface Feed { articles: Article[]; query: string; sources: string[]; updated_at: string }

export function IntelligencePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [feed, setFeed] = useState<Feed | null>(null);
  const [selected, setSelected] = useState<Article | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (keyword: string) => {
    setLoading(true); setError("");
    try {
      const response = await fetch(`/api/public/intelligence?q=${encodeURIComponent(keyword)}&limit=30`);
      if (!response.ok) throw new Error(`情报服务请求失败（${response.status}）`);
      setFeed(await response.json() as Feed);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "情报服务不可用"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(""); }, [load]);
  const submit = (event: FormEvent) => { event.preventDefault(); const value = query.trim(); setSubmitted(value); void load(value); };
  const convert = (article: Article) => { navigate(`/?q=${encodeURIComponent(`分析“${article.title}”对 A 股公司的影响`)}`); document.documentElement.scrollTop = 0; document.body.scrollTop = 0; };

  return <div className="min-h-screen bg-slate-50 text-slate-950"><section className="border-b bg-white"><div className="mx-auto max-w-[1440px] px-8 py-6"><div className="flex items-center gap-2 text-xs font-semibold text-primary"><Newspaper className="h-4 w-4"/> INTELLIGENCE SEARCH</div><h1 className="mt-1 text-2xl font-bold">情报搜索</h1><p className="mt-1 text-sm text-slate-500">搜索真实新闻源并回到原文核验，再将事件转成研究问题</p></div></section><main className="mx-auto max-w-[1440px] px-8 py-5"><form onSubmit={submit} className="flex items-center gap-3 rounded-xl border bg-white p-3 shadow-sm"><Search className="ml-2 h-5 w-5 text-primary"/><input aria-label="情报检索问题" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索公告、新闻与产业信息" className="h-11 flex-1 bg-transparent text-sm outline-none"/><button className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white">智能搜索 <ArrowRight className="h-4 w-4"/></button></form><section className="mt-5 overflow-hidden rounded-xl border bg-white shadow-sm"><div className="flex items-center justify-between border-b px-5 py-4"><div><h2 className="font-semibold">情报速递</h2><p className="mt-1 text-xs text-slate-500">{submitted ? `搜索“${submitted}”` : "最近更新"} · {feed?.articles.length ?? 0} 条</p></div><div className="text-xs text-slate-400">{feed?.sources.join("、") || "等待数据源"}</div></div>{loading && <div className="flex items-center justify-center gap-2 py-20 text-sm text-slate-500"><LoaderCircle className="h-5 w-5 animate-spin"/>正在读取情报源</div>}{error && <div className="m-5 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>}{!loading && !error && feed?.articles.length === 0 && <div className="py-20 text-center text-sm text-slate-500">没有找到匹配的真实情报，请调整关键词。</div>}<div className="divide-y">{feed?.articles.map((article, index) => <article key={`${article.url}-${index}`} className="grid gap-4 px-5 py-5 md:grid-cols-[1fr_auto]"><div><h3><button aria-label={`查看 ${article.title} 新闻详情`} onClick={() => setSelected(article)} className="text-left font-semibold hover:text-primary">{article.title}</button></h3><p className="mt-2 text-sm leading-6 text-slate-600">{article.snippet || "来源未提供摘要，请打开原文核验。"}</p><div className="mt-2 text-xs text-slate-400">{article.source || "来源未知"} · {article.published || "时间未知"}</div></div><div className="flex items-center gap-2"><button onClick={() => setSelected(article)} className="rounded-lg border px-3 py-2 text-xs font-semibold">查看详情</button><button onClick={() => convert(article)} className="inline-flex items-center gap-1 rounded-lg border border-primary/25 px-3 py-2 text-xs font-semibold text-primary"><Sparkles className="h-3.5 w-3.5"/>转为研究问题</button></div></article>)}</div><div className="flex items-center justify-between border-t bg-slate-50 px-5 py-3 text-xs text-slate-500"><span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5"/>结果来自实时聚合服务</span><Link to="/product/data-hub" className="font-semibold text-primary">查看数据能力</Link></div></section></main>{selected && <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30" onMouseDown={() => setSelected(null)}><aside role="dialog" aria-label="情报详情" onMouseDown={e => e.stopPropagation()} className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl"><div className="flex items-start justify-between border-b p-6"><div><div className="text-xs text-slate-500">{selected.source} · {selected.published}</div><h2 className="mt-3 text-xl font-bold leading-8">{selected.title}</h2></div><button aria-label="关闭情报详情" onClick={() => setSelected(null)}><X className="h-5 w-5"/></button></div><div className="flex-1 p-6"><h3 className="text-sm font-semibold">来源摘要</h3><p className="mt-3 text-sm leading-7 text-slate-600">{selected.snippet || "该来源未提供摘要，请查看原文。"}</p><a href={selected.url} target="_blank" rel="noreferrer" className="mt-7 inline-flex items-center gap-2 font-semibold text-primary">查看原文 <ExternalLink className="h-4 w-4"/></a></div><div className="border-t bg-slate-50 p-6"><button onClick={() => convert(selected)} className="w-full rounded-lg bg-primary py-3 text-sm font-semibold text-white">转为 AI 研究问题</button></div></aside></div>}</div>;
}
