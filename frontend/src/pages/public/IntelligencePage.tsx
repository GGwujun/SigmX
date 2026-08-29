import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Database, ExternalLink, LoaderCircle, Newspaper, Search, Sparkles, X } from "lucide-react";

interface Article { title: string; url: string; source: string; published: string; snippet: string }
interface Feed { articles: Article[]; query: string; sources: string[]; updated_at: string; cache_status: "live" | "fresh_cache" | "stale_cache"; cached_until: string | null; degraded?: boolean; warnings?: string[] }

function cacheDescription(status?: Feed["cache_status"]): string {
  if (status === "fresh_cache") return "短期缓存命中 · 减少重复抓取";
  if (status === "stale_cache") return "外部源暂不可用 · 使用 24 小时内缓存";
  return "实时聚合结果 · 已写入短期缓存";
}

export function IntelligencePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [feed, setFeed] = useState<Feed | null>(null);
  const [selected, setSelected] = useState<Article | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (keyword: string) => {
    setLoading(true); setError("");
    try {
      const response = await fetch(`/api/public/intelligence?q=${encodeURIComponent(keyword)}&limit=60`);
      if (!response.ok) throw new Error(`情报服务请求失败（${response.status}）`);
      setFeed(await response.json() as Feed);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "情报服务不可用"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(""); }, [load]);
  const submit = (event: FormEvent) => { event.preventDefault(); const value = query.trim(); setSubmitted(value); setVisibleCount(10); void load(value); };
  const convert = (article: Article) => { navigate(`/?q=${encodeURIComponent(`分析“${article.title}”对 A 股公司的影响`)}`); document.documentElement.scrollTop = 0; document.body.scrollTop = 0; };
  const articles = feed?.articles ?? [];

  return <div className="bg-white text-zinc-950"><main className="mx-auto max-w-[1440px] px-5 py-6 sm:px-8 lg:px-10 lg:py-7">
    <header className="flex flex-col gap-4 border-b border-zinc-100 pb-5 lg:flex-row lg:items-center lg:justify-between"><div><h1 className="text-[24px] font-semibold tracking-[-0.035em]">情报搜索</h1><p className="mt-1 text-[13px] text-zinc-500">搜索真实新闻源，核验信息并转化为研究问题</p></div><form onSubmit={submit} className="flex w-full items-center gap-2 lg:w-[560px]"><label className="relative min-w-0 flex-1"><Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"/><input aria-label="情报检索问题" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索公告、新闻与产业信息" className="h-10 w-full rounded-xl border border-zinc-200 bg-zinc-50/50 pl-10 pr-3 text-[13px] outline-none transition focus:border-zinc-400 focus:bg-white focus:ring-4 focus:ring-zinc-100"/></label><button className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-zinc-950 px-4 text-[12px] font-medium text-white transition hover:bg-zinc-800">智能搜索 <ArrowRight className="h-3.5 w-3.5"/></button></form></header>
    {feed?.degraded && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-800">部分情报源暂不可用，当前结果可能不完整，系统已自动使用其他可用来源。</div>}
    <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_260px]"><section><div className="flex items-end justify-between border-b border-zinc-200 pb-3"><div><h2 className="text-[16px] font-semibold">情报速递</h2><p className="mt-1 text-[11px] text-zinc-400">{submitted ? `搜索“${submitted}”` : "最近更新"} · {articles.length} 条</p></div><span className="max-w-[45%] truncate text-[11px] text-zinc-400">{feed?.sources.join("、") || "等待数据源"}</span></div>
      {loading && <div className="flex items-center justify-center gap-2 py-24 text-sm text-zinc-500"><LoaderCircle className="h-5 w-5 animate-spin"/>正在读取情报源</div>}
      {error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {!loading && !error && articles.length === 0 && <div className="py-20 text-center text-sm text-zinc-500">没有找到匹配的真实情报，请调整关键词。</div>}
      <div className="divide-y divide-zinc-200">{articles.slice(0, visibleCount).map((article, index) => <ArticleRow key={`${article.url}-${index}`} article={article} onOpen={setSelected} onConvert={convert}/>)}</div>
      {visibleCount < articles.length && <div className="mt-5 flex justify-center"><button type="button" onClick={() => setVisibleCount(count => count + 10)} className="rounded-xl border border-zinc-300 px-5 py-2.5 text-[13px] font-medium text-zinc-700 hover:bg-zinc-50">加载更多情报</button></div>}
    </section><FeedSummary feed={feed}/></div>
  </main>{selected && <DetailDrawer article={selected} onClose={() => setSelected(null)} onConvert={convert}/>}</div>;
}

function ArticleRow({ article, onOpen, onConvert }: { article: Article; onOpen: (article: Article) => void; onConvert: (article: Article) => void }) {
  return <article className="group grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"><div className="min-w-0"><div className="mb-2 flex items-center gap-2 text-[12px] text-zinc-500"><span className="rounded-md bg-blue-50 px-2 py-1 font-medium text-blue-700">{article.source || "来源未知"}</span><span>{article.published || "时间未知"}</span></div><h3><button aria-label={`查看 ${article.title} 新闻详情`} onClick={() => onOpen(article)} className="text-left text-[15px] font-semibold leading-6 tracking-[-0.01em] transition hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40">{article.title}</button></h3><p className="mt-1 line-clamp-2 text-[13px] leading-5 text-zinc-500">{article.snippet || "来源未提供摘要，请打开原文核验。"}</p></div><div className="flex items-center sm:opacity-75 sm:transition sm:group-hover:opacity-100"><button aria-label="转为研究问题" onClick={() => onConvert(article)} className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 px-3 py-2 text-[12px] font-medium text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400/40"><Sparkles className="h-3.5 w-3.5"/>转为研究问题</button></div></article>;
}

function FeedSummary({ feed }: { feed: Feed | null }) { return <aside className="h-fit rounded-2xl border border-zinc-200 p-5 xl:sticky xl:top-20"><div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><Newspaper className="h-4 w-4"/></span><h2 className="text-[15px] font-semibold">情报概览</h2></div><dl className="mt-4 divide-y divide-zinc-200 text-[12px]"><div className="flex justify-between py-3"><dt className="text-zinc-500">当前结果</dt><dd className="font-medium">{feed?.articles.length ?? 0} 条</dd></div><div className="flex justify-between py-3"><dt className="text-zinc-500">覆盖来源</dt><dd className="font-medium">{feed?.sources.length ?? 0} 个</dd></div></dl><p className={`mt-3 flex items-start gap-2 text-[11px] leading-5 ${feed?.cache_status === "stale_cache" ? "text-amber-700" : "text-zinc-500"}`}><Database className="mt-0.5 h-3.5 w-3.5 shrink-0"/>{cacheDescription(feed?.cache_status)}</p><Link to="/global-events" className="mt-5 inline-flex items-center gap-1 text-[12px] font-medium text-blue-600 hover:text-blue-800">查看全球事件 <ArrowRight className="h-3.5 w-3.5"/></Link></aside>; }

function DetailDrawer({ article, onClose, onConvert }: { article: Article; onClose: () => void; onConvert: (article: Article) => void }) { return <div className="fixed inset-0 z-50 flex justify-end bg-zinc-950/30" onMouseDown={onClose}><aside role="dialog" aria-label="情报详情" onMouseDown={event => event.stopPropagation()} className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl"><div className="flex items-start justify-between border-b border-zinc-200 p-6"><div><div className="text-xs text-zinc-500">{article.source} · {article.published}</div><h2 className="mt-3 text-xl font-semibold leading-8">{article.title}</h2></div><button aria-label="关闭情报详情" onClick={onClose}><X className="h-5 w-5"/></button></div><div className="flex-1 p-6"><h3 className="text-sm font-semibold">来源摘要</h3><p className="mt-3 text-sm leading-7 text-zinc-600">{article.snippet || "该来源未提供摘要，请查看原文。"}</p><a href={article.url} target="_blank" rel="noreferrer" className="mt-7 inline-flex items-center gap-2 font-semibold text-blue-600">查看原文 <ExternalLink className="h-4 w-4"/></a></div><div className="border-t border-zinc-200 bg-zinc-50 p-6"><button onClick={() => onConvert(article)} className="w-full rounded-xl bg-zinc-950 py-3 text-sm font-semibold text-white">转为 AI 研究问题</button></div></aside></div>; }
