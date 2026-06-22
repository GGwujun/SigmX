import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, Building2, Coins, Cpu, Globe, Landmark, Loader2, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { api, type EventItem, type EventsCategory } from "@/lib/api";
import { cn } from "@/lib/utils";

const REFRESH_INTERVAL_MS = 120_000;
const BIG_MOVE_THRESHOLD = 0.1;

const CATEGORY_ICONS: Record<string, typeof Globe> = {
  geopolitical: Globe,
  politics: Landmark,
  crypto: Coins,
  tech: Cpu,
  world: Building2,
};

function fmtProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function fmtChange(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}pt`;
}

function isBigMove(value: number): boolean {
  return Math.abs(value) >= BIG_MOVE_THRESHOLD;
}

function inferTheme(event: EventItem): { theme: string; direction: string; evidence: string } {
  const text = `${event.title} ${event.threshold}`.toLowerCase();
  if (/ai|chip|semiconductor|nvidia|tech|compute|data center/.test(text)) {
    return { theme: "AI / 半导体", direction: "风险偏好与算力链", evidence: "可作为科技成长方向的外部情绪证据" };
  }
  if (/bitcoin|crypto|ethereum|stablecoin/.test(text)) {
    return { theme: "数字资产 / 金融科技", direction: "情绪映射为风险偏好", evidence: "可作为高风险偏好或金融科技情绪证据" };
  }
  if (/oil|gas|energy|iran|israel|war|russia|ukraine/.test(text)) {
    return { theme: "能源 / 军工 / 避险", direction: "避险或资源价格扰动", evidence: "可作为资源价格、避险情绪或地缘风险证据" };
  }
  if (/tariff|trade|china|export|sanction/.test(text)) {
    return { theme: "出口链 / 贸易摩擦", direction: "外需与关税预期", evidence: "可作为外需、关税和供应链扰动证据" };
  }
  if (/fed|rate|inflation|cpi|treasury|recession|unemployment/.test(text)) {
    return { theme: "宏观流动性", direction: "估值与风险偏好", evidence: "可作为利率、通胀和宽基风险偏好证据" };
  }
  return { theme: "全球事件", direction: "需要人工确认影响路径", evidence: "暂不直接映射到具体标的" };
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  const diff = Date.now() - date.getTime();
  const mins = Math.max(0, Math.floor(diff / 60000));
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  return `${Math.floor(hrs / 24)}天前`;
}

export function GlobalEvents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<EventsCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [activeCat, setActiveCat] = useState(searchParams.get("category") ?? "all");
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback((silent = false) => {
    if (!silent) setRefreshing(true);
    api.listEvents()
      .then((res) => {
        setCategories(res.categories);
        setUpdatedAt(res.updated_at);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "加载全球事件失败");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setActiveCat(searchParams.get("category") ?? "all");
  }, [searchParams]);

  useEffect(() => {
    setLoading(true);
    fetchData(true);
  }, [fetchData]);

  useEffect(() => {
    intervalRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const applySearch = useCallback(() => {
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (activeCat !== "all") next.set("category", activeCat);
    setSearchParams(next);
  }, [activeCat, query, setSearchParams]);

  const allEvents = useMemo(() => {
    return categories.flatMap((cat) => cat.events.map((event) => ({ ...event, categoryId: cat.id, categoryLabel: cat.label })));
  }, [categories]);

  const visibleEvents = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allEvents
      .filter((event) => activeCat === "all" || event.categoryId === activeCat)
      .filter((event) => {
        const inferred = inferTheme(event);
        return !q || `${event.title} ${event.threshold} ${event.categoryLabel} ${event.source} ${inferred.theme}`.toLowerCase().includes(q);
      })
      .sort((a, b) => Math.abs(b.prob_change_24h) - Math.abs(a.prob_change_24h));
  }, [activeCat, allEvents, query]);

  const bigMoveCount = visibleEvents.filter((event) => isBigMove(event.prob_change_24h)).length;

  function updateCategory(nextCategory: string) {
    setActiveCat(nextCategory);
    const next = new URLSearchParams(searchParams);
    if (nextCategory === "all") next.delete("category");
    else next.set("category", nextCategory);
    setSearchParams(next);
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-muted/20">
      {/* Header */}
      <header className="shrink-0 border-b bg-background">
        <div className="flex flex-col gap-4 px-4 py-4 md:px-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold tracking-tight">全球事件</h1>
              <span className="rounded bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">概率市场</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              全球重要事件的发生概率变化，用作今日推荐的外部事件证据源。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") applySearch(); }}
                placeholder="搜索事件或主题"
                className="h-9 w-[200px] rounded-md border bg-background pl-3 pr-3 text-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
              />
            </div>
            <button
              type="button"
              onClick={() => fetchData()}
              disabled={refreshing}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              刷新
            </button>
            {updatedAt && (
              <span className="text-xs text-muted-foreground">更新于 {timeAgo(updatedAt)}</span>
            )}
          </div>
        </div>

        {/* Category filters */}
        <div className="border-t px-4 py-3 md:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <CategoryButton active={activeCat === "all"} label="全部事件" count={allEvents.length} onClick={() => updateCategory("all")} />
            {categories.map((cat) => {
              const Icon = CATEGORY_ICONS[cat.id] || Globe;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => updateCategory(cat.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors",
                    activeCat === cat.id ? "border-primary/40 bg-primary/10 text-primary" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {cat.label}
                  <span className="tabular-nums opacity-70">{cat.events.length}</span>
                </button>
              );
            })}
            <span className="ml-auto text-xs text-muted-foreground">大幅异动 {bigMoveCount} 个</span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto max-w-7xl">
          {loading ? (
            <div className="flex min-h-[360px] items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              正在加载全球事件
            </div>
          ) : error ? (
            <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-md border border-danger/20 bg-danger/5 px-6 text-center">
              <AlertTriangle className="h-9 w-9 text-danger/70" />
              <p className="text-sm text-foreground">数据加载失败</p>
              <p className="max-w-md text-xs text-muted-foreground">{error}</p>
              <button
                type="button"
                onClick={() => fetchData()}
                className="rounded-md border px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
              >
                重试
              </button>
            </div>
          ) : visibleEvents.length === 0 ? (
            <div className="flex min-h-[360px] flex-col items-center justify-center rounded-md border border-dashed bg-background px-6 text-center">
              <Globe className="h-10 w-10 text-muted-foreground/40" />
              <p className="mt-3 text-sm font-medium">当前筛选下暂无事件</p>
              <p className="mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
                切换事件分类或减少关键词限制后再试。
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border bg-card">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">事件</th>
                    <th className="px-3 py-2 text-left font-medium">概率变化</th>
                    <th className="px-3 py-2 text-left font-medium">影响主题</th>
                    <th className="px-3 py-2 text-left font-medium">可能影响</th>
                    <th className="px-3 py-2 text-left font-medium">证据状态</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEvents.map((event) => (
                    <EventRow key={event.id} event={event} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function CategoryButton({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors",
        active ? "border-primary/40 bg-primary/10 text-primary" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {label}
      <span className="tabular-nums opacity-70">{count}</span>
    </button>
  );
}

function EventRow({ event }: { event: EventItem & { categoryLabel?: string; categoryId?: string } }) {
  const inferred = inferTheme(event);
  const big = isBigMove(event.prob_change_24h);

  return (
    <tr className={cn("border-b last:border-0 hover:bg-muted/25", big && "bg-warning/5")}>
      <td className="max-w-[460px] px-3 py-3">
        <p className="line-clamp-2 text-sm font-medium leading-snug">{event.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
          {event.categoryLabel && <span className="rounded bg-muted px-1.5 py-0.5">{event.categoryLabel}</span>}
          {event.threshold && event.threshold !== "-" && <span>{event.threshold}</span>}
          {event.source && <span>{event.source}</span>}
          {event.resolve_time && <span>截止 {event.resolve_time}</span>}
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="min-w-[120px]">
          <p className="text-xs text-muted-foreground">当前 {fmtProbability(event.probability)}</p>
          <p className={cn("mt-1 flex items-center gap-1 text-sm font-semibold tabular-nums", event.prob_change_24h >= 0 ? "text-success" : "text-danger")}>
            {event.prob_change_24h >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            {fmtChange(event.prob_change_24h)}
          </p>
          {big && <span className="mt-1 inline-block rounded bg-warning/15 px-1.5 py-0.5 text-[10px] text-warning">大幅异动</span>}
        </div>
      </td>
      <td className="px-3 py-3">
        <p className="text-xs font-medium">{inferred.theme}</p>
        <p className="mt-1 max-w-[180px] text-[10px] leading-relaxed text-muted-foreground">{inferred.direction}</p>
      </td>
      <td className="px-3 py-3">
        <p className="max-w-[240px] text-xs leading-relaxed text-muted-foreground">{inferred.evidence}</p>
      </td>
      <td className="px-3 py-3">
        <span className={cn("inline-flex rounded px-2 py-1 text-[10px] font-medium", big ? "bg-warning/15 text-warning" : "bg-muted text-muted-foreground")}>
          {big ? "可进入证据池" : "观察"}
        </span>
      </td>
    </tr>
  );
}
