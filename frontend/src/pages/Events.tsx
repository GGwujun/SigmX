import { useState, useEffect, useCallback, useRef } from "react";
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  X,
  Globe,
  Landmark,
  Coins,
  Cpu,
  Building2,
} from "lucide-react";
import { api, type EventItem, type EventsCategory, type HistoryPoint } from "@/lib/api";
import { cn } from "@/lib/utils";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 120_000;
const BIG_MOVE_THRESHOLD = 0.10;

const CATEGORY_ICONS: Record<string, typeof Globe> = {
  geopolitical: Globe,
  politics: Landmark,
  crypto: Coins,
  tech: Cpu,
  world: Building2,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtProbability(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

function fmtChange(c: number): string {
  const sign = c >= 0 ? "+" : "";
  return `${sign}${(c * 100).toFixed(1)}pt`;
}

function isBigMove(c: number): boolean {
  return Math.abs(c) >= BIG_MOVE_THRESHOLD;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProbabilityBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 min-w-[48px] rounded-full bg-muted/50 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.round(value * 100)}%`,
            background: value >= 0.5 ? "hsl(var(--success))" : "hsl(var(--warning))",
          }}
        />
      </div>
      <span className="text-xs tabular-nums font-medium w-12 text-right">{fmtProbability(value)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Probability trend chart
// ---------------------------------------------------------------------------

function ProbabilityChart({
  history,
  eventTitle,
  dark,
}: {
  history: HistoryPoint[];
  eventTitle: string;
  dark: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !history.length) return;

    const theme = getChartTheme();
    const chart = echarts.init(containerRef.current);

    const times = history.map((p) => p.time.slice(0, 10));
    const probs = history.map((p) => Math.round(p.probability * 1000) / 10);

    chart.setOption({
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.tooltipText, fontSize: 12 },
        formatter: (params: { data: number; axisValue: string }[]) => {
          if (!params?.length) return "";
          const p = params[0];
          return `${p.axisValue}<br/><b>${p.data}%</b>`;
        },
      },
      grid: { left: 48, right: 16, top: 16, bottom: 32 },
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
      series: [
        {
          type: "line",
          data: probs,
          smooth: true,
          symbol: "none",
          lineStyle: { color: theme.infoColor, width: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: theme.infoColor + "44" },
              { offset: 1, color: theme.infoColor + "04" },
            ]),
          },
        },
      ],
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [history, eventTitle, dark]);

  if (!history.length) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        暂无历史数据
      </div>
    );
  }

  return <div ref={containerRef} className="w-full h-full" />;
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function DetailPanel({
  event,
  onClose,
  dark,
}: {
  event: EventItem;
  onClose: () => void;
  dark: boolean;
}) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<30 | 90>(30);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    api
      .getEventHistory(event.source, event.id, range)
      .then((res) => {
        if (!alive) return;
        setHistory(res.history);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const msg = err instanceof Error ? err.message : "加载历史数据失败";
        setError(msg);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [event.source, event.id, range]);

  return (
    <div className="border rounded-xl p-4 bg-card space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm leading-snug">{event.title}</h3>
          <p className="text-xs text-muted-foreground mt-1">
            {event.source === "kalshi" ? "Kalshi" : "Polymarket"}
            {event.threshold !== "—" && ` · ${event.threshold}`}
          </p>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
          aria-label="关闭详情"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-muted/40 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold tabular-nums">{fmtProbability(event.probability)}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">当前概率</p>
        </div>
        <div className="bg-muted/40 rounded-lg p-3 text-center">
          <p
            className={cn(
              "text-2xl font-bold tabular-nums flex items-center justify-center gap-1",
              event.prob_change_24h >= 0 ? "text-green-500" : "text-red-500",
            )}
          >
            {event.prob_change_24h >= 0 ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <TrendingDown className="w-4 h-4" />
            )}
            {fmtChange(event.prob_change_24h)}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">24h 变化</p>
        </div>
        <div className="bg-muted/40 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold tabular-nums">{event.volume}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">成交量</p>
        </div>
      </div>

      {/* Resolve time */}
      {event.resolve_time && (
        <p className="text-xs text-muted-foreground">
          揭晓时间:{" "}
          <span className="font-medium text-foreground">
            {event.resolve_time}
          </span>
        </p>
      )}

      {/* Range toggle */}
      <div className="flex items-center gap-1">
        {([30, 90] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={cn(
              "px-2.5 py-0.5 text-xs rounded-md border transition-colors",
              range === r
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted/40 text-muted-foreground border-transparent hover:bg-muted",
            )}
          >
            {r}天
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="h-[280px]">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground gap-2">
            <AlertTriangle className="w-4 h-4" />
            {error}
          </div>
        ) : (
          <ProbabilityChart history={history} eventTitle={event.title} dark={dark} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Events table
// ---------------------------------------------------------------------------

type SortKey = "probability" | "prob_change_24h" | "volume_raw" | "resolve_time";

function EventsTable({
  events,
  selectedId,
  onSelect,
  dark: _dark,
}: {
  events: EventItem[];
  selectedId: string | null;
  onSelect: (e: EventItem) => void;
  dark: boolean;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("prob_change_24h");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const parseVolume = (v: string): number => {
    const cleaned = v.replace(/[$,]/g, "");
    if (cleaned.endsWith("M")) return parseFloat(cleaned) * 1_000_000;
    if (cleaned.endsWith("K")) return parseFloat(cleaned) * 1_000;
    return parseFloat(cleaned) || 0;
  };

  const sorted = [...events].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "probability":
        cmp = a.probability - b.probability;
        break;
      case "prob_change_24h":
        cmp = a.prob_change_24h - b.prob_change_24h;
        break;
      case "volume_raw":
        cmp = parseVolume(a.volume) - parseVolume(b.volume);
        break;
      case "resolve_time":
        cmp = a.resolve_time.localeCompare(b.resolve_time);
        break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? (
      <ChevronUp className="w-3 h-3 inline ml-0.5" />
    ) : (
      <ChevronDown className="w-3 h-3 inline ml-0.5" />
    );
  };

  const thClass =
    "px-3 py-2 text-left text-[11px] font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none whitespace-nowrap";

  if (!events.length) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">
        该分类暂无事件
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className={thClass + " w-full"} onClick={() => toggleSort("prob_change_24h")}>
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
            const isSelected = event.id === selectedId;
            const big = isBigMove(event.prob_change_24h);
            return (
              <tr
                key={event.id}
                onClick={() => onSelect(event)}
                className={cn(
                  "border-b last:border-0 cursor-pointer transition-colors hover:bg-muted/50",
                  isSelected && "bg-primary/5 hover:bg-primary/10 border-primary/20",
                  big && "bg-amber-500/5",
                )}
              >
                <td className="px-3 py-2.5">
                  <p className="text-xs font-medium leading-snug">{event.title}</p>
                  {event.threshold !== "—" && (
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {event.threshold}
                    </p>
                  )}
                  {big && (
                    <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium">
                      大幅异动
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <ProbabilityBar value={event.probability} />
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={cn(
                      "text-xs font-medium tabular-nums flex items-center gap-1",
                      event.prob_change_24h >= 0 ? "text-green-500" : "text-red-500",
                    )}
                  >
                    {event.prob_change_24h >= 0 ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : (
                      <TrendingDown className="w-3 h-3" />
                    )}
                    {fmtChange(event.prob_change_24h)}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-xs tabular-nums text-muted-foreground">
                  {event.volume}
                </td>
                <td className="px-3 py-2.5 text-xs tabular-nums text-muted-foreground whitespace-nowrap">
                  {event.resolve_time}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function Events() {
  const { dark } = useDarkMode();
  const [categories, setCategories] = useState<EventsCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCat, setActiveCat] = useState<string>("geopolitical");
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(
    (silent = false) => {
      if (!silent) setRefreshing(true);

      api
        .listEvents()
        .then((res) => {
          setCategories(res.categories);
          setUpdatedAt(res.updated_at);
          setError(null);

          const firstWithEvents = res.categories.find((c) => c.events.length > 0);
          if (firstWithEvents && !res.categories.find((c) => c.id === activeCat)) {
            setActiveCat(firstWithEvents.id);
          }
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : "加载失败";
          if (!categories.length) setError(msg);
          else toast.error(msg);
        })
        .finally(() => {
          setLoading(false);
          setRefreshing(false);
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Initial load
  useEffect(() => {
    let alive = true;
    setLoading(true);

    api
      .listEvents()
      .then((res) => {
        if (!alive) return;
        setCategories(res.categories);
        setUpdatedAt(res.updated_at);
        const firstWithEvents = res.categories.find((c) => c.events.length > 0);
        if (firstWithEvents) setActiveCat(firstWithEvents.id);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, []);

  // Auto-refresh
  useEffect(() => {
    intervalRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const activeCategory = categories.find((c) => c.id === activeCat);
  const activeEvents = activeCategory?.events ?? [];

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b shrink-0">
        <div>
          <h1 className="text-lg font-semibold">预测市场</h1>
          <p className="text-xs text-muted-foreground">
            Polymarket 实时预测市场事件概率
          </p>
        </div>
        <div className="flex items-center gap-3">
          {updatedAt && (
            <span className="text-[10px] text-muted-foreground hidden sm:inline">
              更新于 {new Date(updatedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => fetchData()}
            disabled={refreshing}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            aria-label="刷新"
          >
            <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Category sidebar */}
        <aside className="w-[160px] shrink-0 border-r overflow-y-auto p-3 space-y-1 hidden md:block">
          {categories.map((cat) => {
            const Icon = CATEGORY_ICONS[cat.id] || Globe;
            const count = cat.events.length;
            return (
              <button
                key={cat.id}
                onClick={() => {
                  setActiveCat(cat.id);
                  setSelectedEvent(null);
                }}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors text-left",
                  activeCat === cat.id
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="flex-1 truncate">{cat.label}</span>
                <span className="text-[10px] tabular-nums opacity-60">{count}</span>
              </button>
            );
          })}
        </aside>

        {/* Mobile category tabs */}
        <div className="md:hidden flex items-center gap-1 px-4 py-2 border-b overflow-x-auto shrink-0">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => {
                setActiveCat(cat.id);
                setSelectedEvent(null);
              }}
              className={cn(
                "px-3 py-1.5 text-xs rounded-full transition-colors whitespace-nowrap",
                activeCat === cat.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Main area: table + optional detail */}
        <div className="flex-1 flex overflow-hidden">
          {/* Table */}
          <div
            className={cn(
              "flex-1 overflow-y-auto",
              selectedEvent ? "hidden lg:block" : "",
            )}
          >
            {/* Source badge */}
            {activeCategory && (
              <div className="px-4 py-2 border-b flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">数据源</span>
                <span className="text-xs font-medium px-2 py-0.5 rounded bg-muted">
                  {activeCategory.source}
                </span>
                <span className="text-[10px] text-muted-foreground ml-auto">
                  {activeEvents.length} 个事件
                </span>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                <AlertTriangle className="w-8 h-8" />
                <p className="text-sm">{error}</p>
                <button
                  onClick={() => fetchData()}
                  className="text-xs text-primary hover:underline"
                >
                  重试
                </button>
              </div>
            ) : (
              <EventsTable
                events={activeEvents}
                selectedId={selectedEvent?.id ?? null}
                onSelect={setSelectedEvent}
                dark={dark}
              />
            )}
          </div>

          {/* Detail panel */}
          {selectedEvent && (
            <div className="hidden lg:block w-[380px] shrink-0 border-l overflow-y-auto p-4">
              <DetailPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} dark={dark} />
            </div>
          )}

          {/* Mobile detail modal */}
          {selectedEvent && (
            <div className="lg:hidden fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
              <div className="absolute inset-x-0 bottom-0 top-12 overflow-y-auto p-4">
                <DetailPanel
                  event={selectedEvent}
                  onClose={() => setSelectedEvent(null)}
                  dark={dark}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
