import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Building2, Coins, Cpu, Globe, Landmark, TrendingDown, TrendingUp } from "lucide-react";
import { api, type EventItem, type EventsCategory } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  MarketEmptyState,
  MarketErrorState,
  MarketIntelHeader,
  MarketLoadingState,
  normalizeChinaSymbol,
  plainSymbol,
} from "@/components/market/MarketIntelShell";

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

function inferTheme(event: EventItem): { theme: string; symbols: string[]; direction: string } {
  const text = `${event.title} ${event.threshold}`.toLowerCase();
  if (/ai|chip|semiconductor|nvidia|tech|compute|data center/.test(text)) {
    return { theme: "AI / 半导体", symbols: ["688981.SH", "002371.SZ", "601138.SH"], direction: "风险偏好与算力链" };
  }
  if (/bitcoin|crypto|ethereum|stablecoin/.test(text)) {
    return { theme: "数字资产 / 金融科技", symbols: ["300059.SZ", "600570.SH"], direction: "情绪映射为风险偏好" };
  }
  if (/oil|gas|energy|iran|israel|war|russia|ukraine/.test(text)) {
    return { theme: "能源 / 军工 / 避险", symbols: ["601857.SH", "600760.SH", "601899.SH"], direction: "避险或资源价格扰动" };
  }
  if (/tariff|trade|china|export|sanction/.test(text)) {
    return { theme: "出口链 / 贸易摩擦", symbols: ["300750.SZ", "002475.SZ", "600104.SH"], direction: "外需与关税预期" };
  }
  if (/fed|rate|inflation|cpi|treasury|recession|unemployment/.test(text)) {
    return { theme: "宏观流动性", symbols: ["510300.SH", "512100.SH"], direction: "估值与风险偏好" };
  }
  return { theme: "全球事件", symbols: [], direction: "需要人工确认映射" };
}

export function Events() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<EventsCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [symbol, setSymbol] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
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
        setError(err instanceof Error ? err.message : "加载事件雷达失败");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setSymbol(plainSymbol(searchParams.get("symbol") ?? ""));
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
    if (symbol.trim()) next.set("symbol", normalizeChinaSymbol(symbol));
    if (activeCat !== "all") next.set("category", activeCat);
    setSearchParams(next);
  }, [activeCat, query, setSearchParams, symbol]);

  const allEvents = useMemo(() => {
    return categories.flatMap((cat) => cat.events.map((event) => ({ ...event, categoryId: cat.id, categoryLabel: cat.label })));
  }, [categories]);

  const visibleEvents = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allEvents
      .filter((event) => activeCat === "all" || event.categoryId === activeCat)
      .filter((event) => {
        const inferred = inferTheme(event);
        return !q || `${event.title} ${event.threshold} ${event.categoryLabel} ${event.source} ${inferred.theme} ${inferred.symbols.join(" ")}`.toLowerCase().includes(q);
      })
      .sort((a, b) => Math.abs(b.prob_change_24h) - Math.abs(a.prob_change_24h));
  }, [activeCat, allEvents, query]);

  const bigMoveCount = visibleEvents.filter((event) => isBigMove(event.prob_change_24h)).length;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <MarketIntelHeader
        active="events"
        query={query}
        symbol={symbol}
        onQueryChange={setQuery}
        onSymbolChange={setSymbol}
        onSearch={applySearch}
        onRefresh={() => fetchData()}
        refreshing={refreshing}
        updatedAt={updatedAt}
      />

      <div className="border-b px-4 py-3 md:px-6">
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

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <MarketLoadingState label="正在加载事件影响映射" />
        ) : error ? (
          <MarketErrorState message={error} onRetry={() => fetchData()} />
        ) : visibleEvents.length === 0 ? (
          <MarketEmptyState
            icon={Globe}
            title="当前筛选下暂无事件"
            description="切换事件分类或减少关键词限制后再试。"
          />
        ) : (
          <div className="overflow-hidden rounded-md border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">事件</th>
                  <th className="px-3 py-2 text-left font-medium">概率变化</th>
                  <th className="px-3 py-2 text-left font-medium">影响主题</th>
                  <th className="px-3 py-2 text-left font-medium">相关标的</th>
                  <th className="px-3 py-2 text-left font-medium">下一步</th>
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
    </div>
  );

  function updateCategory(nextCategory: string) {
    setActiveCat(nextCategory);
    const next = new URLSearchParams(searchParams);
    if (nextCategory === "all") next.delete("category");
    else next.set("category", nextCategory);
    setSearchParams(next);
  }
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
          {event.categoryLabel && <span>{event.categoryLabel}</span>}
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
        <div className="flex max-w-[220px] flex-wrap gap-1.5">
          {inferred.symbols.length ? inferred.symbols.map((symbol) => (
            <Link
              key={symbol}
              to={`/logic-chain?symbol=${encodeURIComponent(symbol)}&q=${encodeURIComponent(event.title)}`}
              className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary hover:bg-primary/15"
            >
              {symbol.replace(/\.(SZ|SH)$/, "")}
            </Link>
          )) : <span className="text-xs text-muted-foreground">待映射</span>}
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="flex min-w-[170px] gap-2">
          <Link to={`/opportunity?q=${encodeURIComponent(event.title)}`} className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:opacity-90">
            进候选池
            <ArrowRight className="h-3 w-3" />
          </Link>
          {inferred.symbols[0] && (
            <Link to={`/logic-chain?symbol=${encodeURIComponent(inferred.symbols[0])}&q=${encodeURIComponent(event.title)}`} className="rounded-md border px-2.5 py-1 text-xs hover:bg-muted">
              看逻辑
            </Link>
          )}
        </div>
      </td>
    </tr>
  );
}
