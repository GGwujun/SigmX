import { useState, useEffect, useCallback, useRef } from "react";
import { Newspaper, Search, Loader2, RefreshCw, ExternalLink, AlertTriangle, ChevronRight } from "lucide-react";
import { api, type NewsArticle } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const REFRESH_MS = 300_000; // 5 min
const LS_NEWS_KEY = "vibe-news-watchlist";

function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(LS_NEWS_KEY);
    if (raw) return JSON.parse(raw).map((p: { symbol: string }) => p.symbol);
  } catch { /* */ }
  return [];
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    const now = Date.now();
    const diff = now - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}分钟前`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}小时前`;
    return `${Math.floor(hrs / 24)}天前`;
  } catch {
    return dateStr;
  }
}

export function News() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [stockNews, setStockNews] = useState<{ code: string; name: string; articles: NewsArticle[] } | null>(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"market" | "watchlist">("market");
  const [watchlistStocks, setWatchlistStocks] = useState<{ code: string; name: string }[]>([]);
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNews = useCallback((q?: string) => {
    setRefreshing(true);
    api.listNews(q)
      .then((res) => {
        setArticles(res.articles);
        setActiveQuery(res.query);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "获取新闻失败");
      })
      .finally(() => setRefreshing(false));
  }, []);

  // Initial load
  useEffect(() => {
    api.listNews()
      .then((res) => { setArticles(res.articles); setActiveQuery(res.query); })
      .catch((err) => setError(err instanceof Error ? err.message : "获取新闻失败"))
      .finally(() => setLoading(false));
  }, []);

  // Auto-refresh
  useEffect(() => {
    intervalRef.current = setInterval(() => fetchNews(activeQuery || undefined), REFRESH_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchNews, activeQuery]);

  // Load watchlist for stock news tab
  useEffect(() => {
    const codes = loadWatchlist();
    // For each code, fetch the name via the position snapshot
    Promise.all(codes.slice(0, 10).map(async (code) => {
      try {
        const snap = await api.getPositionSnapshot(code);
        return { code, name: snap.name };
      } catch {
        return { code, name: code };
      }
    })).then(setWatchlistStocks);
  }, []);

  // Stock news
  const fetchStockNews = (code: string) => {
    setStockLoading(true);
    setSelectedStock(code);
    api.getStockNews(code)
      .then((res) => setStockNews({ code: res.code, name: res.name, articles: res.articles }))
      .catch(() => toast.error("获取股票新闻失败"))
      .finally(() => setStockLoading(false));
  };

  // Search
  const handleSearch = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      fetchNews(searchQuery || undefined);
    }
  };

  const displayArticles = activeTab === "watchlist" && stockNews
    ? stockNews.articles
    : articles;

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b shrink-0">
        <div>
          <h1 className="text-lg font-semibold">新闻</h1>
          <p className="text-xs text-muted-foreground">A股财经要闻 · 新浪财经 + DuckDuckGo</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => fetchNews(activeQuery || undefined)} disabled={refreshing}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors">
            <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-4 md:px-6 py-2 border-b shrink-0 flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearch}
            placeholder="搜索关键词，如 半导体、新能源、茅台..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1">
          {(["market", "watchlist"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => { setActiveTab(tab); setStockNews(null); setSelectedStock(null); }}
              className={cn("px-3 py-1.5 text-xs rounded-md transition-colors",
                activeTab === tab ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {tab === "market" ? "市场要闻" : "自选相关"}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Article list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <AlertTriangle className="w-8 h-8" />
              <p className="text-sm">{error}</p>
              <button onClick={() => fetchNews()} className="text-xs text-primary hover:underline">重试</button>
            </div>
          ) : (
            <div className="divide-y">
              {displayArticles.length === 0 && (
                <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
                  暂无新闻
                </div>
              )}
              {displayArticles.map((a, i) => (
                <a
                  key={a.url || i}
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-3 px-4 md:px-6 py-3 hover:bg-muted/30 transition-colors group"
                >
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium leading-snug group-hover:text-primary transition-colors line-clamp-2">
                      {a.title}
                    </h3>
                    {a.snippet && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{a.snippet}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                      {a.source && <span className="font-medium">{a.source}</span>}
                      {a.published && <span>{timeAgo(a.published)}</span>}
                    </div>
                  </div>
                  <ExternalLink className="w-3.5 h-3.5 shrink-0 mt-1 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Watchlist sidebar */}
        {activeTab === "watchlist" && (
          <aside className="w-[170px] shrink-0 border-l overflow-y-auto p-3 space-y-0.5 hidden md:block">
            <p className="text-[10px] text-muted-foreground font-medium px-1 mb-1">自选股</p>
            {watchlistStocks.length === 0 && (
              <p className="text-[10px] text-muted-foreground px-1">暂无自选股</p>
            )}
            {watchlistStocks.map((s) => (
              <button
                key={s.code}
                onClick={() => fetchStockNews(s.code)}
                className={cn(
                  "w-full flex items-center justify-between px-2 py-1.5 rounded-md text-xs transition-colors text-left",
                  selectedStock === s.code ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <span className="truncate">{s.name}</span>
                {stockLoading && selectedStock === s.code && (
                  <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                )}
                {!stockLoading && <ChevronRight className="w-3 h-3 shrink-0 opacity-40" />}
              </button>
            ))}
          </aside>
        )}
      </div>
    </div>
  );
}
