import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  CalendarDays,
  ChevronDown,
  History,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Star,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { api, type DailyRecommendationBacktestResponse, type DailyRecommendationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const HISTORY_DAYS = 30;

function fmtPct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function fmtPrice(value?: number | null): string {
  if (!value) return "-";
  return value >= 1000 ? value.toFixed(0) : value.toFixed(2);
}

function retTone(value?: number | null): string {
  if (value === undefined || value === null) return "text-muted-foreground";
  if (value > 0) return "text-danger";
  if (value < 0) return "text-success";
  return "text-muted-foreground";
}

function slotLabel(slot: string): string {
  if (slot === "morning") return "9:27";
  if (slot === "afternoon") return "14:30";
  return "手动";
}

function resultLabel(item: DailyRecommendationItem): { label: string; tone: "good" | "bad" | "warn" | "neutral" } {
  const value = item.performance.t3?.return_pct ?? item.performance.t1?.return_pct ?? item.performance.latest_return_pct;
  if (value === undefined || value === null) return { label: "数据不足", tone: "neutral" };
  if (value >= 2) return { label: "命中", tone: "good" };
  if (value <= -2) return { label: "失败", tone: "bad" };
  return { label: "观察中", tone: "warn" };
}

function aiDecisionLabel(value?: string): string {
  if (value === "recommend") return "AI复核通过";
  if (value === "watch") return "AI建议观察";
  if (value === "reject") return "AI剔除";
  return "AI待确认";
}

function factorTone(score?: number): "good" | "bad" | "warn" | "neutral" {
  if (score === undefined) return "neutral";
  if (score >= 0.6) return "good";
  if (score <= 0.4) return "bad";
  return "warn";
}

function factorLabel(item: DailyRecommendationItem): string {
  return item.factor_review?.summary || "因子待确认";
}

function recommendationStrength(item: DailyRecommendationItem): {
  label: string;
  score: number;
  stars: number;
  tone: "good" | "warn" | "neutral";
} {
  const base = Number.isFinite(item.score) ? item.score : 0.5;
  const ai = item.ai_review?.score;
  const factor = item.factor_review?.score;
  const score = base * 0.5 + (ai ?? base) * 0.3 + (factor ?? base) * 0.2;
  const normalized = Math.max(0.01, Math.min(0.99, score));

  if (normalized >= 0.78) return { label: "强推荐", score: normalized, stars: 5, tone: "good" };
  if (normalized >= 0.66) return { label: "偏强", score: normalized, stars: 4, tone: "good" };
  if (normalized >= 0.54) return { label: "中性", score: normalized, stars: 3, tone: "warn" };
  return { label: "观察", score: normalized, stars: 2, tone: "neutral" };
}

export function RecommendationHistory() {
  const [selectedDate, setSelectedDate] = useState("latest");
  const [query, setQuery] = useState("");
  const [resultFilter, setResultFilter] = useState<"all" | "good" | "warn" | "bad">("all");
  const [data, setData] = useState<DailyRecommendationBacktestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getDailyRecommendationBacktest(HISTORY_DAYS));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载推荐历史失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dateOptions = useMemo(() => {
    return Array.from(new Set((data?.items ?? []).map((item) => item.date))).sort((a, b) => b.localeCompare(a));
  }, [data]);

  const effectiveDate = selectedDate === "latest" ? dateOptions[0] ?? "" : selectedDate;

  const groups = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const items = (data?.items ?? []).filter((item) => {
      const result = resultLabel(item);
      const matchDate = item.date === effectiveDate;
      const matchResult = resultFilter === "all" || result.tone === resultFilter;
      const matchKeyword = !keyword || item.name.toLowerCase().includes(keyword) || item.symbol.toLowerCase().includes(keyword);
      return matchDate && matchResult && matchKeyword;
    });
    const byDate = new Map<string, DailyRecommendationItem[]>();
    for (const item of items) {
      const rows = byDate.get(item.date) ?? [];
      rows.push(item);
      byDate.set(item.date, rows);
    }
    return Array.from(byDate.entries())
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, rows]) => ({
        date,
        rows: rows.sort((a, b) => {
          if (a.slot !== b.slot) return a.slot === "morning" ? -1 : 1;
          return a.rank - b.rank;
        }),
      }));
  }, [data, effectiveDate, query, resultFilter]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-muted/20">
      <header className="shrink-0 border-b bg-background px-4 py-4 md:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold tracking-tight">推荐复盘</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">复盘历史推荐的后续表现，只展示推荐发生时固化的证据快照。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              刷新
            </button>
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在加载历史表现
          </div>
        ) : !data || data.items.length === 0 ? (
          <Empty />
        ) : (
          <div className="mx-auto max-w-7xl space-y-4">
            <Summary data={data} />
            <Filters
              dateOptions={dateOptions}
              selectedDate={selectedDate}
              onDateChange={setSelectedDate}
              query={query}
              onQueryChange={setQuery}
              resultFilter={resultFilter}
              onResultFilterChange={setResultFilter}
            />
            {groups.length === 0 ? (
              <FilteredEmpty effectiveDate={effectiveDate} />
            ) : (
              groups.map((group) => (
                <HistoryDay
                  key={group.date}
                  date={group.date}
                  items={group.rows}
                  expandedId={expandedId}
                  onToggle={(id) => setExpandedId((current) => current === id ? null : id)}
                />
              ))
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Empty() {
  return (
    <div className="mx-auto flex min-h-[360px] max-w-3xl flex-col items-center justify-center rounded-md border border-dashed bg-background px-6 text-center">
      <CalendarDays className="h-10 w-10 text-muted-foreground/40" />
      <p className="mt-3 text-sm font-medium">暂无推荐历史</p>
      <p className="mt-1 text-xs text-muted-foreground">生成过每日推荐后，这里会自动累积表现。</p>
    </div>
  );
}

function FilteredEmpty({ effectiveDate }: { effectiveDate: string }) {
  return (
    <div className="flex min-h-[260px] items-center justify-center rounded-md border border-dashed bg-background px-6 text-center">
      <div>
        <CalendarDays className="mx-auto h-9 w-9 text-muted-foreground/40" />
        <p className="mt-3 text-sm font-medium">当前筛选下暂无推荐</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {`${effectiveDate || "最新一次推荐日"} 没有匹配的推荐记录，可以切换其他交易日。`}
        </p>
      </div>
    </div>
  );
}

function Summary({ data }: { data: DailyRecommendationBacktestResponse }) {
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <Metric label="近30天推荐数" value={`${data.summary.count}`} />
      <Metric label="近30天T+1样本" value={`${data.summary.t1_count}`} />
      <Metric label="近30天T+1胜率" value={data.summary.t1_win_rate === null ? "-" : `${data.summary.t1_win_rate}%`} />
      <Metric label="近30天T+1均值" value={fmtPct(data.summary.t1_avg_return)} tone={retTone(data.summary.t1_avg_return)} />
    </section>
  );
}

function Filters({
  dateOptions,
  selectedDate,
  onDateChange,
  query,
  onQueryChange,
  resultFilter,
  onResultFilterChange,
}: {
  dateOptions: string[];
  selectedDate: string;
  onDateChange: (value: string) => void;
  query: string;
  onQueryChange: (value: string) => void;
  resultFilter: "all" | "good" | "warn" | "bad";
  onResultFilterChange: (value: "all" | "good" | "warn" | "bad") => void;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-md border bg-card p-3 md:flex-row md:items-center">
      <select
        value={selectedDate}
        onChange={(event) => onDateChange(event.target.value)}
        className="h-9 rounded-md border bg-background px-3 text-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
      >
        <option value="latest">最新一次推荐{dateOptions[0] ? `（${dateOptions[0]}）` : ""}</option>
        {selectedDate !== "latest" && !dateOptions.includes(selectedDate) && (
          <option value={selectedDate}>{selectedDate}（暂无记录）</option>
        )}
        {dateOptions.map((date) => (
          <option key={date} value={date}>{date}</option>
        ))}
      </select>
      <select
        value={resultFilter}
        onChange={(event) => onResultFilterChange(event.target.value as "all" | "good" | "warn" | "bad")}
        className="h-9 rounded-md border bg-background px-3 text-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
      >
        <option value="all">全部结论</option>
        <option value="good">命中</option>
        <option value="warn">观察中</option>
        <option value="bad">失败</option>
      </select>
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索股票名称或代码"
          className="h-9 w-full rounded-md border bg-background pl-9 pr-3 text-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
        />
      </div>
    </section>
  );
}

function Metric({ label, value, tone, compact }: { label: string; value: string; tone?: string; compact?: boolean }) {
  return (
    <div className={cn("rounded-md border bg-card", compact ? "px-3 py-2" : "p-4")}>
      <p className={cn(compact ? "text-sm" : "text-xl", "font-semibold tabular-nums", tone)}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

function HistoryDay({
  date,
  items,
  expandedId,
  onToggle,
}: {
  date: string;
  items: DailyRecommendationItem[];
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  const avg = items.length ? items.reduce((sum, item) => sum + (item.performance.latest_return_pct ?? 0), 0) / items.length : 0;
  return (
    <section className="overflow-hidden rounded-md border bg-card">
      <div className="flex flex-col gap-1 border-b bg-background px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">{date}</p>
          <p className="text-xs text-muted-foreground">{items.length} 条推荐</p>
        </div>
        <span className={cn("text-xs font-semibold tabular-nums", retTone(avg))}>当前平均 {fmtPct(avg)}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1040px] text-sm">
          <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">股票</th>
              <th className="px-3 py-2 text-left font-medium">时段</th>
              <th className="px-3 py-2 text-left font-medium">强度</th>
              <th className="px-3 py-2 text-left font-medium">来源/策略</th>
              <th className="px-3 py-2 text-left font-medium">推荐理由</th>
              <th className="px-3 py-2 text-right font-medium">推荐价</th>
              <th className="px-3 py-2 text-right font-medium">T+0</th>
              <th className="px-3 py-2 text-right font-medium">T+1</th>
              <th className="px-3 py-2 text-right font-medium">T+3</th>
              <th className="px-3 py-2 text-right font-medium">T+5</th>
              <th className="px-3 py-2 text-right font-medium">最新</th>
              <th className="px-3 py-2 text-left font-medium">结果</th>
              <th className="px-3 py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const open = expandedId === item.id;
              const result = resultLabel(item);
              return (
                <Fragment key={item.id}>
                  <tr className={cn("border-b hover:bg-muted/25", open && "bg-primary/5")}>
                    <td className="px-3 py-3">
                      <p className="text-xs font-medium">{item.name}</p>
                      <p className="font-mono text-[10px] text-muted-foreground">{item.symbol}</p>
                    </td>
                    <td className="px-3 py-3 text-xs">{slotLabel(item.slot)}</td>
                    <td className="px-3 py-3">
                      <StrengthBadge item={item} />
                    </td>
                    <td className="px-3 py-3">
                      <p className="text-xs text-muted-foreground">{item.strategy || item.category}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <StatusBadge label={aiDecisionLabel(item.ai_review?.decision)} tone={item.ai_review?.decision === "recommend" ? "good" : "warn"} />
                        <StatusBadge label={factorLabel(item)} tone={factorTone(item.factor_review?.score)} />
                      </div>
                    </td>
                    <td className="max-w-[260px] px-3 py-3 text-xs text-muted-foreground">
                      <p className="line-clamp-2">{item.reason || "暂无推荐理由"}</p>
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-xs">¥{fmtPrice(item.price_at_pick)}</td>
                    <ReturnCell value={item.performance.t0?.return_pct} />
                    <ReturnCell value={item.performance.t1?.return_pct} />
                    <ReturnCell value={item.performance.t3?.return_pct} />
                    <ReturnCell value={item.performance.t5?.return_pct} />
                    <ReturnCell value={item.performance.latest_return_pct} icon />
                    <td className="px-3 py-3">
                      <StatusBadge label={result.label} tone={result.tone} />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => onToggle(item.id)}
                          className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs hover:bg-muted"
                        >
                          复盘
                          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b bg-primary/5">
                      <td colSpan={13} className="px-4 py-4">
                        <HistoryDetail item={item} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HistoryDetail({ item }: { item: DailyRecommendationItem }) {
  const p = item.performance;
  return (
    <div className="grid gap-3 xl:grid-cols-[1fr_1fr_1.2fr]">
      <DetailBlock icon={Target} title="当时为什么推荐" body={item.reason || "暂无推荐理由"} />
      <DetailBlock icon={ShieldAlert} title="风险/失效条件" body={item.risk_note || "如果价格、量能或板块同步性转弱，推荐假设需要降级。"} muted />
      <EvidenceSnapshotBlock item={item} />
      <div className="xl:col-span-3">
        <PerformanceBlock latest={p.latest_return_pct} maxGain={p.max_gain_pct} maxDrawdown={p.max_drawdown_pct} />
      </div>
    </div>
  );
}

function EvidenceSnapshotBlock({ item }: { item: DailyRecommendationItem }) {
  const snapshot = item.evidence_snapshot;
  const fallbackMarket = `推荐时价格 ¥${fmtPrice(item.price_at_pick)}，日内涨跌幅 ${fmtPct(item.change_pct_at_pick)}`;
  const bullish = snapshot?.bullish_factors?.filter(Boolean) ?? item.factor_review?.top_bullish?.map((entry) => entry.label || "").filter(Boolean).slice(0, 3) ?? [];
  const bearish = snapshot?.bearish_factors?.filter(Boolean) ?? item.factor_review?.top_bearish?.map((entry) => entry.label || "").filter(Boolean).slice(0, 3) ?? [];
  const rows = [
    { label: "行情证据", value: snapshot?.market || fallbackMarket },
    { label: "候选信号", value: snapshot?.scanner || item.reason },
    { label: "AI复核", value: snapshot?.ai || item.ai_review?.summary },
    { label: "因子证据", value: snapshot?.factor || item.factor_review?.summary },
  ].filter((row) => row.value);

  return (
    <div className="rounded-md border bg-background px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Sparkles className="h-4 w-4 text-primary" />
        当时证据快照
      </div>
      <p className="mb-3 text-[11px] leading-5 text-muted-foreground">
        {snapshot?.source || "推荐生成时记录的证据；复盘时不重新查询新闻、事件或逻辑链。"}
      </p>
      <div className="space-y-2">
        {rows.map((row) => (
          <EvidenceLine key={row.label} label={row.label} value={row.value || "-"} />
        ))}
        {bullish.length > 0 && <EvidenceLine label="偏强因子" value={bullish.join("、")} />}
        {bearish.length > 0 && <EvidenceLine label="偏弱因子" value={bearish.join("、")} />}
      </div>
    </div>
  );
}

function EvidenceLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <p className="text-[10px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-xs leading-5 text-foreground">{value}</p>
    </div>
  );
}

function PerformanceBlock({ latest, maxGain, maxDrawdown }: { latest?: number; maxGain?: number; maxDrawdown?: number }) {
  return (
    <div className="grid gap-2 rounded-md border bg-background p-3 md:grid-cols-3">
      <Metric label="最新收益" value={fmtPct(latest)} tone={retTone(latest)} compact />
      <Metric label="期间最大涨幅" value={fmtPct(maxGain)} tone={retTone(maxGain)} compact />
      <Metric label="期间最大回撤" value={fmtPct(maxDrawdown)} tone={retTone(maxDrawdown)} compact />
    </div>
  );
}

function DetailBlock({
  icon: Icon,
  title,
  body,
  muted,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  muted?: boolean;
}) {
  return (
    <div className={cn("rounded-md border px-4 py-3", muted ? "bg-background/70" : "bg-background")}>
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Icon className={cn("h-4 w-4", muted ? "text-warning" : "text-primary")} />
        {title}
      </div>
      <p className="text-sm leading-6 text-foreground">{body}</p>
    </div>
  );
}

function ReturnCell({ value, icon }: { value?: number | null; icon?: boolean }) {
  return (
    <td className={cn("px-3 py-3 text-right text-xs font-semibold tabular-nums", retTone(value))}>
      {icon && value !== undefined && value !== null && (
        value >= 0 ? <TrendingUp className="mr-1 inline h-3 w-3" /> : <TrendingDown className="mr-1 inline h-3 w-3" />
      )}
      {fmtPct(value)}
    </td>
  );
}

function StrengthBadge({ item }: { item: DailyRecommendationItem }) {
  const strength = recommendationStrength(item);
  return (
    <div className="min-w-[86px]">
      <div
        className={cn(
          "inline-flex items-center gap-0.5 rounded px-2 py-1",
          strength.tone === "good" && "bg-success/10 text-success",
          strength.tone === "warn" && "bg-warning/10 text-warning",
          strength.tone === "neutral" && "bg-muted text-muted-foreground",
        )}
        title={`综合强度 ${strength.score.toFixed(2)}，由推荐分、AI评分和因子评分加权得到`}
      >
        {Array.from({ length: 5 }).map((_, index) => (
          <Star
            key={index}
            className={cn("h-3 w-3", index < strength.stars ? "fill-current" : "opacity-25")}
          />
        ))}
      </div>
      <p className="mt-1 text-[10px] font-medium text-muted-foreground">{strength.label} · {strength.score.toFixed(2)}</p>
    </div>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: "good" | "bad" | "warn" | "neutral" }) {
  return (
    <span
      className={cn(
        "inline-flex rounded px-2 py-1 text-[10px] font-medium",
        tone === "good" && "bg-success/10 text-success",
        tone === "bad" && "bg-danger/10 text-danger",
        tone === "warn" && "bg-warning/10 text-warning",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}
