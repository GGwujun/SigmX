import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  ChevronDown,
  Clock3,
  GitBranch,
  History,
  Loader2,
  Newspaper,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { api, type DailyRecommendationBacktestResponse, type DailyRecommendationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

type SlotFilter = "all" | "morning" | "afternoon";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

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
  if (value > 0) return "text-success";
  if (value < 0) return "text-danger";
  return "text-muted-foreground";
}

function slotName(slot: string): string {
  if (slot === "morning") return "9:27";
  if (slot === "afternoon") return "14:30";
  return "手动";
}

function slotTitle(slot: string): string {
  if (slot === "morning") return "早盘";
  if (slot === "afternoon") return "尾盘";
  return "手动";
}

export function DailyRecommendations() {
  const [items, setItems] = useState<DailyRecommendationItem[]>([]);
  const [backtest, setBacktest] = useState<DailyRecommendationBacktestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState<"morning" | "afternoon" | null>(null);
  const [date, setDate] = useState(today());
  const [slotFilter, setSlotFilter] = useState<SlotFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, bt] = await Promise.all([
        api.listDailyRecommendations({ date, limit: 100 }),
        api.getDailyRecommendationBacktest(30),
      ]);
      setItems(list.items);
      setBacktest(bt);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载每日推荐失败");
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    load();
  }, [load]);

  const sorted = useMemo(() => {
    return items
      .filter((item) => slotFilter === "all" || item.slot === slotFilter)
      .sort((a, b) => {
        if (a.slot !== b.slot) return a.slot === "morning" ? -1 : 1;
        return a.rank - b.rank;
      });
  }, [items, slotFilter]);

  useEffect(() => {
    if (!sorted.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !sorted.some((item) => item.id === selectedId)) {
      setSelectedId(sorted[0].id);
      setEvidenceOpen(false);
    }
  }, [selectedId, sorted]);

  const selected = sorted.find((item) => item.id === selectedId) ?? sorted[0] ?? null;
  const stats = backtest?.summary;

  const generate = async (slot: "morning" | "afternoon") => {
    setGenerating(slot);
    try {
      await api.generateDailyRecommendations(slot, 5);
      toast.success(`${slotName(slot)} 推荐已生成`);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成推荐失败");
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-muted/20">
      <header className="shrink-0 border-b bg-background">
        <div className="flex flex-col gap-4 px-4 py-4 md:px-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold tracking-tight">今日推荐</h1>
              <span className="rounded bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">决策页</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              先看能不能买，再看为什么，最后看历史准不准。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="h-9 rounded-md border bg-background px-3 text-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
            />
            <ActionButton
              icon={Clock3}
              label="生成 9:27"
              busy={generating === "morning"}
              disabled={generating !== null}
              onClick={() => generate("morning")}
              primary
            />
            <ActionButton
              icon={Sparkles}
              label="生成 14:30"
              busy={generating === "afternoon"}
              disabled={generating !== null}
              onClick={() => generate("afternoon")}
            />
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              刷新
            </button>
            <Link
              to="/recommendation-history"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <History className="h-3.5 w-3.5" />
              历史
            </Link>
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-hidden">
        <div className="grid h-full grid-rows-[auto_1fr]">
          <SummaryBar
            count={sorted.length}
            total={stats?.count ?? 0}
            t1WinRate={stats?.t1_win_rate}
            t1AvgReturn={stats?.t1_avg_return}
            slotFilter={slotFilter}
            onSlotFilterChange={setSlotFilter}
          />

          {loading ? (
            <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              正在加载推荐
            </div>
          ) : sorted.length === 0 ? (
            <EmptyState date={date} />
          ) : (
            <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[380px_minmax(0,1fr)]">
              <RecommendationQueue
                items={sorted}
                selectedId={selected?.id ?? null}
                onSelect={(item) => {
                  setSelectedId(item.id);
                  setEvidenceOpen(false);
                }}
              />
              {selected && (
                <DecisionPanel
                  item={selected}
                  evidenceOpen={evidenceOpen}
                  onToggleEvidence={() => setEvidenceOpen((value) => !value)}
                />
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function SummaryBar({
  count,
  total,
  t1WinRate,
  t1AvgReturn,
  slotFilter,
  onSlotFilterChange,
}: {
  count: number;
  total: number;
  t1WinRate?: number | null;
  t1AvgReturn?: number | null;
  slotFilter: SlotFilter;
  onSlotFilterChange: (value: SlotFilter) => void;
}) {
  return (
    <section className="border-b bg-background px-4 py-3 md:px-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex w-fit rounded-md border bg-muted/30 p-1">
          <Segment label="全部" active={slotFilter === "all"} onClick={() => onSlotFilterChange("all")} />
          <Segment label="9:27" active={slotFilter === "morning"} onClick={() => onSlotFilterChange("morning")} />
          <Segment label="14:30" active={slotFilter === "afternoon"} onClick={() => onSlotFilterChange("afternoon")} />
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <SummaryMetric label="当前列表" value={`${count}`} />
          <SummaryMetric label="近30天推荐" value={`${total}`} />
          <SummaryMetric label="T+1胜率" value={t1WinRate === null || t1WinRate === undefined ? "-" : `${t1WinRate}%`} />
          <SummaryMetric label="T+1均值" value={fmtPct(t1AvgReturn)} tone={retTone(t1AvgReturn)} />
        </div>
      </div>
    </section>
  );
}

function Segment({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-7 rounded px-3 text-xs font-medium transition",
        active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

function RecommendationQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: DailyRecommendationItem[];
  selectedId: string | null;
  onSelect: (item: DailyRecommendationItem) => void;
}) {
  return (
    <aside className="min-h-0 border-b bg-background lg:border-b-0 lg:border-r">
      <div className="flex h-11 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">推荐队列</span>
        </div>
        <span className="text-xs text-muted-foreground">{items.length} 个标的</span>
      </div>
      <div className="max-h-[42vh] overflow-y-auto p-2 lg:max-h-none lg:h-[calc(100vh-13.25rem)]">
        {items.map((item) => {
          const selected = item.id === selectedId;
          const latest = item.performance.latest_return_pct;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                "mb-1 grid w-full grid-cols-[42px_1fr_auto] items-center gap-3 rounded-md border px-3 py-3 text-left transition",
                selected
                  ? "border-primary/45 bg-primary/5 shadow-[inset_3px_0_0_hsl(var(--primary))]"
                  : "border-transparent hover:border-border hover:bg-muted/50",
              )}
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-muted text-xs font-semibold text-muted-foreground">
                #{item.rank}
              </div>
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-semibold">{item.name}</span>
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{item.symbol}</span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{slotName(item.slot)}</span>
                  <span className="h-1 w-1 rounded-full bg-muted-foreground/40" />
                  <span className="truncate">{item.strategy || item.category || "综合信号"}</span>
                </div>
              </div>
              <div className="text-right">
                <p className={cn("text-sm font-semibold tabular-nums", retTone(latest))}>{fmtPct(latest)}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">当前</p>
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function DecisionPanel({
  item,
  evidenceOpen,
  onToggleEvidence,
}: {
  item: DailyRecommendationItem;
  evidenceOpen: boolean;
  onToggleEvidence: () => void;
}) {
  const p = item.performance;
  const scorePct = Math.round(item.score * 100);
  const latest = p.latest_return_pct;

  return (
    <section className="min-h-0 overflow-y-auto p-4 md:p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="rounded-md border bg-background">
          <div className="border-b px-4 py-4 md:px-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
                    {slotTitle(item.slot)} {slotName(item.slot)} #{item.rank}
                  </span>
                  <span className="rounded bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{item.strategy || "综合推荐"}</span>
                </div>
                <div className="mt-3 flex flex-wrap items-end gap-x-3 gap-y-1">
                  <h2 className="text-2xl font-semibold tracking-tight">{item.name}</h2>
                  <span className="pb-0.5 font-mono text-sm text-muted-foreground">{item.symbol}</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 sm:min-w-[360px]">
                <BigMetric label="信号强度" value={`${scorePct}`} helper="越高越优先" />
                <BigMetric label="推荐价" value={`¥${fmtPrice(item.price_at_pick)}`} helper={item.date} />
                <BigMetric label="当前表现" value={fmtPct(latest)} helper={p.latest_date ?? "未收盘"} tone={retTone(latest)} />
              </div>
            </div>
          </div>

          <div className="grid gap-0 xl:grid-cols-[1fr_320px]">
            <div className="space-y-4 p-4 md:p-5">
              <DecisionBlock
                icon={Target}
                title="推荐理由"
                body={item.reason || "暂无一句话理由"}
              />
              <DecisionBlock
                icon={ShieldAlert}
                title="失效条件"
                body={item.risk_note || "如果价格、量能或板块同步性转弱，推荐假设需要降级。"}
                muted
              />

              <div>
                <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  推荐后表现
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  <Horizon label="T+0" point={p.t0} />
                  <Horizon label="T+1" point={p.t1} />
                  <Horizon label="T+3" point={p.t3} />
                  <Horizon label="T+5" point={p.t5} />
                </div>
              </div>
            </div>

            <aside className="border-t bg-muted/20 p-4 md:p-5 xl:border-l xl:border-t-0">
              <div className="space-y-3">
                <SignalBar score={scorePct} />
                <CompactMetric label="最大浮盈" value={fmtPct(p.max_gain_pct)} tone={retTone(p.max_gain_pct)} />
                <CompactMetric label="最大回撤" value={fmtPct(p.max_drawdown_pct)} tone={retTone(p.max_drawdown_pct)} />
                <CompactMetric label="推荐来源" value={item.source || "system"} />
              </div>

              <div className="mt-5 grid gap-2">
                <Link
                  to={`/tracking-dashboard?symbol=${encodeURIComponent(item.symbol)}`}
                  className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground transition hover:opacity-90"
                >
                  加入跟踪
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
                <button
                  type="button"
                  onClick={onToggleEvidence}
                  className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border bg-background px-3 text-xs transition hover:bg-muted"
                >
                  展开证据
                  <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", evidenceOpen && "rotate-180")} />
                </button>
              </div>
            </aside>
          </div>
        </div>

        {evidenceOpen && <EvidencePanel item={item} />}
      </div>
    </section>
  );
}

function EmptyState({ date }: { date: string }) {
  return (
    <div className="flex items-center justify-center p-6">
      <div className="flex min-h-[360px] w-full max-w-2xl flex-col items-center justify-center rounded-md border border-dashed bg-background px-6 text-center">
        <CalendarDays className="h-10 w-10 text-muted-foreground/40" />
        <p className="mt-3 text-sm font-medium">{date} 还没有推荐</p>
        <p className="mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
          交易日会在 9:27 和 14:30 自动生成，也可以用右上角按钮手动生成。
        </p>
      </div>
    </div>
  );
}

function EvidencePanel({ item }: { item: DailyRecommendationItem }) {
  const q = encodeURIComponent(item.reason || item.name);
  const symbol = encodeURIComponent(item.symbol);
  return (
    <section className="rounded-md border bg-background p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2">
        <Search className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">证据入口</h3>
        <span className="text-xs text-muted-foreground">需要追问时再看</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <EvidenceLink icon={Newspaper} label="新闻证据" to={`/news?symbol=${symbol}&q=${q}`} />
        <EvidenceLink icon={TrendingUp} label="事件证据" to={`/events?q=${q}&symbol=${symbol}`} />
        <EvidenceLink icon={Search} label="候选池来源" to={`/opportunity?symbol=${symbol}`} />
        <EvidenceLink icon={GitBranch} label="完整逻辑链" to={`/logic-chain?symbol=${symbol}&q=${q}`} />
      </div>
    </section>
  );
}

function ActionButton({
  icon: Icon,
  label,
  busy,
  disabled,
  onClick,
  primary,
}: {
  icon: LucideIcon;
  label: string;
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition disabled:opacity-50",
        primary ? "bg-primary text-primary-foreground hover:opacity-90" : "border hover:bg-muted",
      )}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
      {label}
    </button>
  );
}

function SummaryMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2">
      <p className={cn("text-sm font-semibold tabular-nums", tone)}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

function BigMetric({ label, value, helper, tone }: { label: string; value: string; helper: string; tone?: string }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2">
      <p className={cn("text-base font-semibold tabular-nums", tone)}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-[10px] text-muted-foreground/75">{helper}</p>
    </div>
  );
}

function CompactMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border bg-background px-3 py-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-semibold tabular-nums", tone)}>{value}</span>
    </div>
  );
}

function DecisionBlock({
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
    <div className={cn("rounded-md border px-4 py-3", muted ? "bg-muted/25" : "bg-background")}>
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Icon className={cn("h-4 w-4", muted ? "text-warning" : "text-primary")} />
        {title}
      </div>
      <p className="text-sm leading-6 text-foreground">{body}</p>
    </div>
  );
}

function SignalBar({ score }: { score: number }) {
  return (
    <div className="rounded-md border bg-background px-3 py-3">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">信号强度</span>
        <span className="font-semibold tabular-nums">{score}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(score, 100))}%` }} />
      </div>
    </div>
  );
}

function Horizon({ label, point }: { label: string; point?: { return_pct: number; date: string } | null }) {
  return (
    <div className="rounded-md border bg-background px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-base font-semibold tabular-nums", retTone(point?.return_pct))}>{fmtPct(point?.return_pct)}</p>
      <p className="mt-1 truncate text-[10px] text-muted-foreground/75">{point?.date ?? "等待数据"}</p>
    </div>
  );
}

function EvidenceLink({ icon: Icon, label, to }: { icon: LucideIcon; label: string; to: string }) {
  return (
    <Link
      to={to}
      className="flex items-center justify-between rounded-md border bg-card px-3 py-3 text-xs transition hover:border-primary/35 hover:bg-primary/5"
    >
      <span className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-primary" />
        {label}
      </span>
      <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
    </Link>
  );
}

export function RecommendationBacktestSummary({ backtest }: { backtest: DailyRecommendationBacktestResponse | null }) {
  if (!backtest) return null;
  return (
    <section className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">近 30 天表现</h2>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <SummaryMetric label="推荐数" value={`${backtest.summary.count}`} />
        <SummaryMetric label="T+1样本" value={`${backtest.summary.t1_count}`} />
        <SummaryMetric label="T+1胜率" value={backtest.summary.t1_win_rate === null ? "-" : `${backtest.summary.t1_win_rate}%`} />
        <SummaryMetric label="T+1均值" value={fmtPct(backtest.summary.t1_avg_return)} tone={retTone(backtest.summary.t1_avg_return)} />
      </div>
    </section>
  );
}
