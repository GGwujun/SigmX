import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ExternalLink, Newspaper, PlusCircle, Search, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";
import { api, type NewsArticle } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  buildIntelPath,
  MarketEmptyState,
  MarketErrorState,
  MarketIntelHeader,
  MarketLoadingState,
  normalizeChinaSymbol,
  plainSymbol,
} from "@/components/market/MarketIntelShell";

const REFRESH_MS = 300_000;

type Direction = "positive" | "negative" | "neutral";

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  const diff = Date.now() - date.getTime();
  const mins = Math.max(0, Math.floor(diff / 60000));
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} 小时前`;
  return `${Math.floor(hrs / 24)} 天前`;
}

function extractSymbols(article: NewsArticle): string[] {
  const text = `${article.title} ${article.snippet}`;
  const matches = text.match(/\b(?:00|30|60|68)\d{4}\b/g) ?? [];
  return Array.from(new Set(matches)).slice(0, 4);
}

function directionOf(article: NewsArticle): Direction {
  const text = `${article.title} ${article.snippet}`;
  if (/下滑|下降|亏损|处罚|风险|暴跌|减持|不及预期|终止|调查/.test(text)) return "negative";
  if (/增长|突破|中标|增持|回购|超预期|涨价|订单|利好|创新高/.test(text)) return "positive";
  return "neutral";
}

function impactLevel(article: NewsArticle, symbols: string[]): "高" | "中" | "低" {
  const text = `${article.title} ${article.snippet}`;
  if (symbols.length > 0 || /超预期|重大|政策|订单|涨价|减持|回购|处罚/.test(text)) return "高";
  if (/行业|板块|会议|数据|出口|进口|监管/.test(text)) return "中";
  return "低";
}

function directionLabel(direction: Direction): string {
  if (direction === "positive") return "利好";
  if (direction === "negative") return "利空";
  return "待确认";
}

function directionClass(direction: Direction): string {
  if (direction === "positive") return "bg-success/10 text-success";
  if (direction === "negative") return "bg-danger/10 text-danger";
  return "bg-warning/10 text-warning";
}

export function News() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [symbol, setSymbol] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
  const [activeQuery, setActiveQuery] = useState(searchParams.get("q") ?? "");
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNews = useCallback((nextQuery?: string, silent = false) => {
    if (!silent) setRefreshing(true);
    const normalized = symbol.trim() ? normalizeChinaSymbol(symbol) : "";
    const request = normalized ? api.getStockNews(normalized) : api.listNews(nextQuery || undefined);
    request
      .then((res) => {
        setArticles(res.articles);
        setActiveQuery("query" in res ? res.query : res.name);
        setUpdatedAt(res.updated_at);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "获取新闻线索失败");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, [symbol]);

  const applySearch = useCallback(() => {
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (symbol.trim()) next.set("symbol", normalizeChinaSymbol(symbol));
    setSearchParams(next);
    fetchNews(query.trim() || undefined);
  }, [fetchNews, query, setSearchParams, symbol]);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setSymbol(plainSymbol(searchParams.get("symbol") ?? ""));
  }, [searchParams]);

  useEffect(() => {
    setLoading(true);
    fetchNews(searchParams.get("q") || undefined, true);
  }, [fetchNews, searchParams]);

  useEffect(() => {
    intervalRef.current = setInterval(() => fetchNews(activeQuery || undefined, true), REFRESH_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [activeQuery, fetchNews]);

  const clues = useMemo(() => {
    return articles.map((article, index) => {
      const symbols = extractSymbols(article);
      const direction = directionOf(article);
      return {
        id: article.url || `${article.title}-${index}`,
        article,
        symbols,
        direction,
        impact: impactLevel(article, symbols),
      };
    });
  }, [articles]);

  return (
    <div className="flex h-full flex-col">
      <MarketIntelHeader
        active="news"
        query={query}
        symbol={symbol}
        onQueryChange={setQuery}
        onSymbolChange={setSymbol}
        onSearch={applySearch}
        onRefresh={() => fetchNews(activeQuery || undefined)}
        refreshing={refreshing}
        updatedAt={updatedAt}
      />

      <div className="border-b px-4 py-3 md:px-6">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">可交易新闻线索</p>
            <p className="text-xs text-muted-foreground">
              目标不是读完新闻，而是判断它能否进入候选池、每日推荐或逻辑链证据。
            </p>
          </div>
          <span className="text-xs text-muted-foreground">{activeQuery ? `当前主题：${activeQuery}` : "市场综合线索"}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <MarketLoadingState label="正在提取新闻线索" />
        ) : error ? (
          <MarketErrorState message={error} onRetry={() => fetchNews(activeQuery || undefined)} />
        ) : clues.length === 0 ? (
          <MarketEmptyState
            icon={Newspaper}
            title="暂无新闻线索"
            description="换一个主题或输入标的代码后再试。"
          />
        ) : (
          <div className="overflow-hidden rounded-md border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">影响</th>
                  <th className="px-3 py-2 text-left font-medium">新闻线索</th>
                  <th className="px-3 py-2 text-left font-medium">方向</th>
                  <th className="px-3 py-2 text-left font-medium">相关标的</th>
                  <th className="px-3 py-2 text-left font-medium">下一步</th>
                </tr>
              </thead>
              <tbody>
                {clues.map((clue) => (
                  <tr key={clue.id} className="border-b last:border-0 hover:bg-muted/25">
                    <td className="px-3 py-3">
                      <span className={cn(
                        "rounded px-2 py-1 text-xs font-semibold",
                        clue.impact === "高" ? "bg-danger/10 text-danger" : clue.impact === "中" ? "bg-warning/10 text-warning" : "bg-muted text-muted-foreground",
                      )}>
                        {clue.impact}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <a
                        href={clue.article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group inline-flex items-start gap-1.5 text-sm font-medium leading-snug hover:text-primary"
                      >
                        <span className="line-clamp-2">{clue.article.title}</span>
                        <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-45 group-hover:opacity-100" />
                      </a>
                      {clue.article.snippet && (
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{clue.article.snippet}</p>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                        {clue.article.source && <span className="rounded bg-muted px-1.5 py-0.5">{clue.article.source}</span>}
                        {clue.article.published && <span>{timeAgo(clue.article.published)}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <span className={cn("inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium", directionClass(clue.direction))}>
                        {clue.direction === "positive" ? <TrendingUp className="h-3 w-3" /> : clue.direction === "negative" ? <TrendingDown className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
                        {directionLabel(clue.direction)}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {clue.symbols.length ? clue.symbols.map((item) => {
                          const next = new URLSearchParams(searchParams);
                          next.set("symbol", normalizeChinaSymbol(item));
                          next.set("q", clue.article.title);
                          return (
                            <Link
                              key={item}
                              to={buildIntelPath("/logic-chain", next)}
                              className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary hover:bg-primary/15"
                            >
                              {item}
                            </Link>
                          );
                        }) : <span className="text-xs text-muted-foreground">待映射</span>}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex min-w-[170px] gap-2">
                        <Link to={`/opportunity?q=${encodeURIComponent(clue.article.title)}`} className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs hover:bg-muted">
                          <PlusCircle className="h-3.5 w-3.5" />
                          进候选池
                        </Link>
                        <Link to={`/events?q=${encodeURIComponent(clue.article.title)}`} className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs hover:bg-muted">
                          <Search className="h-3.5 w-3.5" />
                          查事件
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
