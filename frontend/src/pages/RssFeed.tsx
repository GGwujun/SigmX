import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Clock3,
  ExternalLink,
  MoreHorizontal,
  Newspaper,
  RefreshCw,
  Rss,
  Sparkles,
  Star,
  Wifi,
  WifiOff,
} from "lucide-react";
import { api, type RssArticle, type RssSource } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  MarketEmptyState,
  MarketErrorState,
  MarketLoadingState,
} from "@/components/market/MarketIntelShell";

const REFRESH_MS = 300_000; // 5 min auto-refresh

function formatTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sourceInitial(name: string) {
  return name.trim().charAt(0).toUpperCase() || "R";
}

export function RssFeed() {
  const [sources, setSources] = useState<RssSource[]>([]);
  const [articles, setArticles] = useState<RssArticle[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<RssArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFeeds = useCallback((source?: string | null, silent = false) => {
    if (!silent) setRefreshing(true);
    api.listRsshubFeeds(source || undefined)
      .then((res) => {
        setSources(res.sources);
        setArticles(res.articles);
        setSelectedSource(res.selected_source);
        setUpdatedAt(res.updated_at);
        setError(null);
        setSelectedArticle((current) => {
          if (!res.articles.length) return null;
          const stillVisible = current && res.articles.find((article) => article.id === current.id);
          return stillVisible || res.articles[0];
        });
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "获取信息流失败");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  const handleSourceClick = useCallback((sourceName: string | null) => {
    setSelectedSource(sourceName);
    setSelectedArticle(null);
    setLoading(true);
    fetchFeeds(sourceName);
  }, [fetchFeeds]);

  const handleArticleClick = useCallback((article: RssArticle) => {
    setSelectedArticle(article);
  }, []);

  const handleRefresh = useCallback(() => {
    fetchFeeds(selectedSource);
  }, [fetchFeeds, selectedSource]);

  useEffect(() => {
    fetchFeeds();
  }, [fetchFeeds]);

  useEffect(() => {
    intervalRef.current = setInterval(() => fetchFeeds(selectedSource, true), REFRESH_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchFeeds, selectedSource]);

  const healthyCount = useMemo(() => sources.filter((source) => source.healthy).length, [sources]);
  const totalArticles = useMemo(() => articles.length, [articles]);
  const selectedSourceMeta = useMemo(
    () => sources.find((source) => source.name === selectedSource),
    [selectedSource, sources],
  );

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-0 flex-col overflow-hidden bg-card text-foreground">
      <header className="shrink-0 border-b bg-card px-4 py-2.5 md:px-5">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <Rss className="h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0 leading-tight">
              <h1 className="truncate text-base font-semibold tracking-tight">RSSHub 信息台</h1>
              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {healthyCount}/{sources.length} 源在线 · {totalArticles} 条资讯
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {updatedAt && <span className="whitespace-nowrap">更新于 {formatTime(updatedAt)}</span>}
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border bg-background px-3 font-medium text-foreground transition-colors",
                "hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
              刷新
            </button>
          </div>
        </div>
      </header>

      <div
        className="grid min-h-0 flex-1 overflow-hidden"
        style={{ gridTemplateColumns: "208px minmax(360px, 400px) minmax(0, 1fr)" }}
      >
        <aside className="min-h-0 border-r bg-[#f4f4f5] dark:bg-card/50">
          <div className="flex h-full flex-col">
            <div className="px-4 pb-2 pt-4">
              <p className="text-xs font-semibold text-muted-foreground">订阅源</p>
            </div>
            <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
              <button
                type="button"
                onClick={() => handleSourceClick(null)}
                className={cn(
                  "group flex h-9 w-full items-center rounded-md px-2.5 text-left text-sm transition-colors",
                  selectedSource === null
                    ? "bg-primary/15 text-foreground font-medium border-l-2 border-primary"
                    : "text-muted-foreground hover:bg-card/70 hover:text-foreground",
                )}
              >
                <Newspaper className="h-4 w-4 shrink-0" />
                <span className="ml-2 min-w-0 flex-1 truncate font-medium">全部</span>
                <span className="ml-2 min-w-8 rounded-full bg-background px-2 py-0.5 text-center text-xs text-muted-foreground">
                  {totalArticles}
                </span>
              </button>

              {sources.map((source) => (
                <button
                  key={source.name}
                  type="button"
                  onClick={() => handleSourceClick(source.name)}
                  className={cn(
                    "group flex h-9 w-full items-center rounded-md px-2.5 text-left text-sm transition-colors",
                    selectedSource === source.name
                      ? "bg-primary/15 text-foreground font-medium border-l-2 border-primary"
                      : "text-muted-foreground hover:bg-card/70 hover:text-foreground",
                  )}
                  title={source.desc ? `${source.name}：${source.desc}` : source.name}
                >
                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm text-[11px] font-semibold"
                    style={{
                      backgroundColor: `${source.color}18`,
                      color: source.color,
                    }}
                  >
                    {sourceInitial(source.name)}
                  </span>
                  <span className="ml-2 min-w-0 flex-1 truncate">{source.name}</span>
                  <span className="ml-2 flex w-11 shrink-0 items-center justify-end gap-1.5">
                    <span className="text-xs tabular-nums text-muted-foreground">{source.count}</span>
                    {source.healthy ? (
                      <Wifi className="h-3 w-3 shrink-0 text-success" />
                    ) : (
                      <WifiOff className="h-3 w-3 shrink-0 text-danger" />
                    )}
                  </span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        <aside className="min-h-0 border-r bg-card">
          <div className="flex h-full flex-col">
            <div className="flex shrink-0 items-center justify-between border-b px-4 py-3">
              <div className="flex items-center gap-2 min-w-0">
                <h2 className="truncate text-base font-semibold">
                  {selectedSourceMeta?.name || "全部文章"}
                </h2>
                <span className="text-xs text-muted-foreground">
                  {selectedSourceMeta?.desc || "按发布时间聚合订阅源内容"}
                </span>
              </div>
              <button
                type="button"
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="更多"
              >
                <MoreHorizontal className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              {loading ? (
                <div className="p-5">
                  <MarketLoadingState label="加载中..." />
                </div>
              ) : error ? (
                <div className="p-5">
                  <MarketErrorState message={error} onRetry={handleRefresh} />
                </div>
              ) : articles.length === 0 ? (
                <div className="p-5">
                  <MarketEmptyState
                    icon={Rss}
                    title="暂无资讯"
                    description={selectedSource ? `「${selectedSource}」暂无内容` : "所有订阅源暂无内容"}
                  />
                </div>
              ) : (
                <ul>
                  {articles.map((article) => {
                    const selected = selectedArticle?.id === article.id;
                    return (
                      <li key={article.id} className="border-b last:border-b-0">
                        <button
                          type="button"
                          onClick={() => handleArticleClick(article)}
                          className={cn(
                            "flex w-full gap-3 px-4 py-3.5 text-left transition-colors",
                            selected
                              ? "bg-primary/15 border-l-2 border-primary"
                              : "hover:bg-muted/45",
                          )}
                        >
                          <span
                            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
                            style={{
                              backgroundColor: `${article.source_color}14`,
                              color: article.source_color,
                            }}
                          >
                            {sourceInitial(article.source)}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                              <span className="truncate">{article.source}</span>
                              {article.published_ago && (
                                <>
                                  <span>·</span>
                                  <span className="shrink-0">{article.published_ago}</span>
                                </>
                              )}
                            </span>
                            <span className="line-clamp-2 text-base font-medium leading-snug text-foreground">
                              {article.title}
                            </span>
                            {article.snippet && (
                              <span className="mt-1.5 line-clamp-2 text-sm leading-snug text-muted-foreground">
                                {article.snippet}
                              </span>
                            )}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </aside>

        <main className="min-h-0 overflow-y-auto bg-card">
          {selectedArticle ? (
            <article
              className="mx-auto"
              style={{ maxWidth: 820, padding: "20px 20px" }}
            >
              <div className="mb-7 flex items-center justify-between gap-4">
                <div className="flex min-w-0 flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-2 font-medium text-foreground">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-sm text-xs font-semibold text-white"
                      style={{ backgroundColor: selectedArticle.source_color }}
                    >
                      {sourceInitial(selectedArticle.source)}
                    </span>
                    {selectedArticle.source}
                  </span>
                  {selectedArticle.published_ago && (
                    <span className="inline-flex items-center gap-1.5">
                      <Clock3 className="h-4 w-4" />
                      {selectedArticle.published_ago}
                    </span>
                  )}
                  {selectedArticle.published && <span>{formatTime(selectedArticle.published)}</span>}
                </div>
                <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
                  <button
                    type="button"
                    className="rounded-md p-2 transition-colors hover:bg-muted hover:text-foreground"
                    aria-label="标记已读"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className="rounded-md p-2 transition-colors hover:bg-muted hover:text-foreground"
                    aria-label="收藏"
                  >
                    <Star className="h-4 w-4" />
                  </button>
                  {selectedArticle.url && (
                    <a
                      href={selectedArticle.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-md p-2 transition-colors hover:bg-muted hover:text-foreground"
                      aria-label="查看原文"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
              </div>

              <h1
                className={cn(
                  "max-w-[760px] font-bold leading-tight tracking-tight text-foreground",
                  selectedArticle.title.length > 56
                    ? "text-xl xl:text-2xl"
                    : "text-[30px] xl:text-4xl",
                )}
              >
                {selectedArticle.title}
              </h1>

              {selectedArticle.snippet && (
                <div className="mt-8 mb-6 rounded-md border bg-background/65 px-6 py-5 shadow-sm shadow-black/[0.02] xl:mt-10 xl:mb-8">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-primary">
                    <Sparkles className="h-4 w-4" />
                    AI 总结
                  </div>
                  <p className="text-base leading-8 text-muted-foreground">{selectedArticle.snippet}</p>
                </div>
              )}

              <div
                className={cn(
                  "prose prose-base mt-10 max-w-none prose-headings:tracking-tight prose-p:leading-9 prose-a:text-primary xl:prose-lg",
                  "prose-img:rounded-md prose-blockquote:border-primary/40 prose-blockquote:text-muted-foreground",
                  "dark:prose-invert",
                )}
                dangerouslySetInnerHTML={{
                  __html: selectedArticle.content || selectedArticle.snippet || "<p>暂无内容摘要</p>",
                }}
              />
            </article>
          ) : (
            <div className="flex h-full items-center justify-center px-6">
              <div className="text-center text-muted-foreground">
                <Circle className="mx-auto mb-4 h-12 w-12 opacity-25" />
                <p className="text-sm">点击中间文章查看详情</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
