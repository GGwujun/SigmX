import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Building2,
  ChevronDown,
  ChevronUp,
  Coins,
  Cpu,
  Globe,
  Landmark,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { api, type EventItem, type EventsCategory, type HistoryPoint } from "@/lib/api";
import { cn } from "@/lib/utils";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";
import {
  buildIntelPath,
  MarketEmptyState,
  MarketErrorState,
  MarketIntelHeader,
  MarketLoadingState,
  normalizeChinaSymbol,
  plainSymbol,
} from "@/components/market/MarketIntelShell";
import { toast } from "sonner";

const REFRESH_INTERVAL_MS = 120_000;
const BIG_MOVE_THRESHOLD = 0.1;

const CATEGORY_ICONS: Record<string, typeof Globe> = {
  geopolitical: Globe,
  politics: Landmark,
  crypto: Coins,
  tech: Cpu,
  world: Building2,
};

type SortKey = "probability" | "prob_change_24h" | "volume_raw" | "resolve_time";

function fmtProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function fmtChange(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}pt`;
}

function isBigMove(value: number): boolean {
  return Math.abs(value) >= BIG_MOVE_THRESHOLD;
}

function parseVolume(value: string): number {
  const cleaned = value.replace(/[$,]/g, "");
  if (cleaned.endsWith("M")) return parseFloat(cleaned) * 1_000_000;
  if (cleaned.endsWith("K")) return parseFloat(cleaned) * 1_000;
  return parseFloat(cleaned) || 0;
}

export function Events() {
  const { dark } = useDarkMode();
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<EventsCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [symbol, setSymbol] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
  const [activeCat, setActiveCat] = useState(searchParams.get("category") ?? "all");
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null);
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
        if (activeCat !== "all" && !res.categories.some((cat) => cat.id === activeCat)) {
          setActiveCat("all");
        }
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "加载事件雷达失败";
        if (!categories.length) setError(msg);
        else toast.error(msg);
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, [activeCat, categories.length]);

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
    return categories.flatMap((cat) => cat.events.map((event) => ({ ...event, categoryId: cat.id, categoryLabel: cat.label, categorySource: cat.source })));
  }, [categories]);

  const visibleEvents = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allEvents
      .filter((event) => activeCat === "all" || event.categoryId === activeCat)
      .filter((event) => !q || `${event.title} ${event.threshold} ${event.categoryLabel} ${event.source}`.toLowerCase().includes(q));
  }, [activeCat, allEvents, query]);

  const bigMoveCount = visibleEvents.filter((event) => isBigMove(event.prob_change_24h)).length;
  const maxMove = visibleEvents.reduce((max, event) => Math.max(max, Math.abs(event.prob_change_24h)), 0);

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
        </div>
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_380px]">
        <main className={cn("min-w-0 overflow-y-auto", selectedEvent && "hidden lg:block")}>
          <div className="grid gap-3 border-b p-4 md:grid-cols-3 md:px-6">
            <StatCard label="当前事件" value={`${visibleEvents.length}`} />
            <StatCard label="大幅异动" value={`${bigMoveCount}`} />
            <StatCard label="最大变化" value={fmtChange(maxMove)} />
          </div>

          <div className="p-4 md:p-6">
            {loading ? (
              <MarketLoadingState label="正在加载事件雷达" />
            ) : error ? (
              <MarketErrorState message={error} onRetry={() => fetchData()} />
            ) : visibleEvents.length === 0 ? (
              <MarketEmptyState
                icon={Globe}
                title="当前筛选下暂无事件"
                description="可以切换事件分类，或减少关键词限制后再试。"
              />
            ) : (
              <EventsTable
                events={visibleEvents}
                selectedId={selectedEvent?.id ?? null}
                onSelect={setSelectedEvent}
              />
            )}
          </div>
        </main>

        <aside className={cn("border-l bg-muted/10", !selectedEvent && "hidden lg:block")}>
          {selectedEvent ? (
            <DetailPanel
              event={selectedEvent}
              dark={dark}
              params={searchParams}
              symbol={symbol}
              onClose={() => setSelectedEvent(null)}
            />
          ) : (
            <div className="p-4">
              <MarketEmptyState
                icon={Globe}
                title="选择一个事件查看详情"
                description="详情里会展示概率历史，并提供进入机会清单和逻辑链的下一步动作。"
              />
            </div>
          )}
        </aside>
      </div>
    </div>
  );

  function updateCategory(nextCategory: string) {
    setActiveCat(nextCategory);
    setSelectedEvent(null);
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

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function ProbabilityBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 min-w-[52px] flex-1 overflow-hidden rounded-full bg-muted/60">
        <div
          className={cn("h-full rounded-full", value >= 0.5 ? "bg-green-500" : "bg-amber-500")}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="w-12 text-right text-xs font-medium tabular-nums">{fmtProbability(value)}</span>
    </div>
  );
}

function EventsTable({
  events,
  selectedId,
  onSelect,
}: {
  events: Array<EventItem & { categoryLabel?: string; categoryId?: string; categorySource?: string }>;
  selectedId: string | null;
  onSelect: (event: EventItem) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("prob_change_24h");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    return [...events].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "probability") cmp = a.probability - b.probability;
      if (sortKey === "prob_change_24h") cmp = a.prob_change_24h - b.prob_change_24h;
      if (sortKey === "volume_raw") cmp = parseVolume(a.volume) - parseVolume(b.volume);
      if (sortKey === "resolve_time") cmp = a.resolve_time.localeCompare(b.resolve_time);
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [events, sortDir, sortKey]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((prev) => (prev === "desc" ? "asc" : "desc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? <ChevronUp className="ml-0.5 inline h-3 w-3" /> : <ChevronDown className="ml-0.5 inline h-3 w-3" />;
  };

  const thClass = "px-3 py-2 text-left text-[11px] font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none whitespace-nowrap";

  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/25">
            <th className={`${thClass} w-full`} onClick={() => toggleSort("prob_change_24h")}>
              事件 <SortIcon col="prob_change_24h" />
            </th>
            <th className={thClass} onClick={() => toggleSort("probability")}>
              概率 <SortIcon col="probability" />
            </th>
            <th className={thClass} onClick={() => toggleSort("prob_change_24h")}>
              24h 变化 <SortIcon col="prob_change_24h" />
            </th>
            <th className={thClass} onClick={() => toggleSort("volume_raw")}>
              成交量 <SortIcon col="volume_raw" />
            </th>
            <th className={thClass} onClick={() => toggleSort("resolve_time")}>
              揭晓 <SortIcon col="resolve_time" />
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((event) => {
            const selected = event.id === selectedId;
            const big = isBigMove(event.prob_change_24h);
            return (
              <tr
                key={event.id}
                onClick={() => onSelect(event)}
                className={cn(
                  "cursor-pointer border-b transition-colors last:border-0 hover:bg-muted/50",
                  selected && "bg-primary/5 hover:bg-primary/10",
                  big && "bg-amber-500/5",
                )}
              >
                <td className="px-3 py-3">
                  <p className="text-xs font-medium leading-snug">{event.title}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                    {event.categoryLabel && <span>{event.categoryLabel}</span>}
                    {event.threshold && event.threshold !== "-" && <span>{event.threshold}</span>}
                    {big && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-600 dark:text-amber-400">大幅异动</span>}
                  </div>
                </td>
                <td className="px-3 py-3">
                  <ProbabilityBar value={event.probability} />
                </td>
                <td className="px-3 py-3">
                  <span className={cn("flex items-center gap-1 text-xs font-medium tabular-nums", event.prob_change_24h >= 0 ? "text-green-500" : "text-red-500")}>
                    {event.prob_change_24h >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                    {fmtChange(event.prob_change_24h)}
                  </span>
                </td>
                <td className="px-3 py-3 text-xs tabular-nums text-muted-foreground">{event.volume}</td>
                <td className="whitespace-nowrap px-3 py-3 text-xs tabular-nums text-muted-foreground">{event.resolve_time}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DetailPanel({
  event,
  dark,
  params,
  symbol,
  onClose,
}: {
  event: EventItem;
  dark: boolean;
  params: URLSearchParams;
  symbol: string;
  onClose: () => void;
}) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<30 | 90>(30);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.getEventHistory(event.source, event.id, range)
      .then((res) => {
        if (alive) setHistory(res.history);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "加载历史数据失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [event.id, event.source, range]);

  const next = new URLSearchParams(params);
  next.set("q", event.title);
  if (symbol.trim()) next.set("symbol", normalizeChinaSymbol(symbol));

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold leading-snug">{event.title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {event.source}
              {event.threshold && event.threshold !== "-" ? ` · ${event.threshold}` : ""}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <DetailMetric label="当前概率" value={fmtProbability(event.probability)} />
          <DetailMetric label="24h 变化" value={fmtChange(event.prob_change_24h)} trend={event.prob_change_24h >= 0 ? "up" : "down"} />
          <DetailMetric label="成交量" value={event.volume} />
        </div>

        {event.resolve_time && (
          <p className="mt-3 text-xs text-muted-foreground">
            揭晓时间：<span className="text-foreground">{event.resolve_time}</span>
          </p>
        )}

        <div className="mt-4 flex items-center gap-1">
          {([30, 90] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setRange(item)}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs transition-colors",
                range === item ? "border-primary bg-primary text-primary-foreground" : "border-transparent bg-muted/50 text-muted-foreground hover:bg-muted",
              )}
            >
              {item} 天
            </button>
          ))}
        </div>

        <div className="mt-4 h-[260px] rounded-lg border bg-background/60 p-2">
          {loading ? (
            <MarketLoadingState label="正在加载概率历史" />
          ) : error ? (
            <MarketErrorState message={error} />
          ) : (
            <ProbabilityChart history={history} dark={dark} />
          )}
        </div>

        <div className="mt-4 space-y-2">
          <Link to={buildIntelPath("/opportunity", next)} className="block rounded-md bg-primary px-3 py-2 text-center text-xs font-medium text-primary-foreground hover:opacity-90">
            查看机会候选
          </Link>
          {symbol.trim() ? (
            <Link to={buildIntelPath("/logic-chain", next)} className="block rounded-md border px-3 py-2 text-center text-xs hover:bg-muted">
              进入标的逻辑链
            </Link>
          ) : (
            <p className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              输入标的代码后，可直接从事件进入逻辑链。
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailMetric({
  label,
  value,
  trend,
}: {
  label: string;
  value: string;
  trend?: "up" | "down";
}) {
  return (
    <div className="rounded-lg bg-muted/40 p-3 text-center">
      <p className={cn("text-lg font-semibold tabular-nums", trend === "up" && "text-green-500", trend === "down" && "text-red-500")}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

function ProbabilityChart({ history, dark }: { history: HistoryPoint[]; dark: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !history.length) return;
    const theme = getChartTheme();
    const chart = echarts.init(containerRef.current);
    const times = history.map((point) => point.time.slice(0, 10));
    const probs = history.map((point) => Math.round(point.probability * 1000) / 10);

    chart.setOption({
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.tooltipText, fontSize: 12 },
        formatter: (params: { data: number; axisValue: string }[]) => {
          if (!params?.length) return "";
          const point = params[0];
          return `${point.axisValue}<br/><b>${point.data}%</b>`;
        },
      },
      grid: { left: 42, right: 12, top: 12, bottom: 28 },
      xAxis: {
        type: "category",
        data: times,
        axisLine: { lineStyle: { color: theme.axisColor } },
        axisLabel: { color: theme.textColor, fontSize: 10, rotate: times.length > 30 ? 45 : 0 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: theme.textColor, fontSize: 11, formatter: "{value}%" },
        splitLine: { lineStyle: { color: theme.gridColor } },
      },
      series: [{
        type: "line",
        data: probs,
        smooth: true,
        symbol: "none",
        lineStyle: { color: theme.infoColor, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: `${theme.infoColor}44` },
            { offset: 1, color: `${theme.infoColor}04` },
          ]),
        },
      }],
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [dark, history]);

  if (!history.length) {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">暂无历史数据</div>;
  }

  return <div ref={containerRef} className="h-full w-full" />;
}
