import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowLeft, Filter, History, Loader2, RefreshCw, TrendingDown, TrendingUp, Zap } from "lucide-react";
import { api, type ArbitrageSignal, type SignalStats } from "@/lib/api";
import { cn } from "@/lib/utils";

type FilterType = "ALL" | "PREMIUM" | "DISCOUNT";
type TabKey = "active" | "history";

const FILTER_OPTIONS: { value: FilterType; label: string }[] = [
  { value: "ALL", label: "全部" },
  { value: "PREMIUM", label: "溢价信号" },
  { value: "DISCOUNT", label: "折价信号" },
];

function fmtPct(v: number, digits = 2): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function signalTone(signal: ArbitrageSignal): string {
  return signal.signal_type === "PREMIUM" ? "text-danger" : "text-success";
}

function signalBg(signal: ArbitrageSignal): string {
  return signal.signal_type === "PREMIUM" ? "bg-danger/5 border-danger/20" : "bg-success/5 border-success/20";
}

function zScoreLabel(z: number): { label: string; tone: string } {
  const abs = Math.abs(z);
  if (abs >= 3) return { label: "极端", tone: "bg-danger text-danger-foreground" };
  if (abs >= 2) return { label: "强", tone: "bg-warning text-warning-foreground" };
  return { label: "弱", tone: "bg-muted text-muted-foreground" };
}

function StatCard({ label, value, sub, icon, tone }: {
  label: string; value: string | number; sub?: string; icon: React.ReactNode; tone?: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <div className={cn("mt-2 text-2xl font-bold tabular-nums", tone)}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function SignalRow({ signal }: { signal: ArbitrageSignal }) {
  const z = zScoreLabel(signal.z_score);
  return (
    <div className={cn("rounded-lg border p-4 transition-colors hover:bg-muted/40", signalBg(signal))}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: code + name + type */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold">{signal.code}</span>
            <span className="truncate text-sm text-muted-foreground">{signal.name}</span>
            <span className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              signal.type === "ETF" ? "bg-blue-500/10 text-blue-600 dark:text-blue-400" : "bg-purple-500/10 text-purple-600 dark:text-purple-400"
            )}>
              {signal.type}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-4 text-sm">
            <span className={cn("font-semibold", signalTone(signal))}>
              {signal.signal_type === "PREMIUM" ? (
                <span className="inline-flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" />溢价</span>
              ) : (
                <span className="inline-flex items-center gap-1"><TrendingDown className="h-3.5 w-3.5" />折价</span>
              )}
            </span>
            <span className="tabular-nums">{fmtPct(signal.premium_rate)}</span>
            <span className="text-muted-foreground">Z={signal.z_score.toFixed(2)}</span>
          </div>
        </div>

        {/* Right: stats */}
        <div className="flex items-center gap-3 text-right">
          <div>
            <div className="text-xs text-muted-foreground">净空间</div>
            <div className={cn("font-semibold tabular-nums", signal.net_spread > 0 ? "text-success" : "text-danger")}>
              {fmtPct(signal.net_spread)}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">历史均值</div>
            <div className="tabular-nums text-muted-foreground">{fmtPct(signal.historical_mean)}</div>
          </div>
          <span className={cn("rounded px-2 py-0.5 text-[10px] font-medium", z.tone)}>
            {z.label}
          </span>
        </div>
      </div>

      {/* Bottom: metadata */}
      <div className="mt-3 flex items-center gap-4 border-t pt-2 text-xs text-muted-foreground">
        <span>日期: {signal.trade_date}</span>
        <span>样本数: {signal.n_history}</span>
        <span>成本: {fmtPct(signal.cost_estimate)}</span>
        <span className={cn(
          "rounded px-1.5 py-0.5",
          signal.status === "active" ? "bg-green-500/10 text-green-600 dark:text-green-400" : "bg-muted"
        )}>
          {signal.status === "active" ? "活跃" : signal.status}
        </span>
        <Link
          to={`/fund-arbitrage?code=${encodeURIComponent(signal.code)}`}
          className="ml-auto text-primary hover:underline"
        >
          深度分析 →
        </Link>
      </div>
    </div>
  );
}

export function Signals() {
  const [tab, setTab] = useState<TabKey>("active");
  const [filter, setFilter] = useState<FilterType>("ALL");
  const [activeSignals, setActiveSignals] = useState<ArbitrageSignal[]>([]);
  const [historySignals, setHistorySignals] = useState<ArbitrageSignal[]>([]);
  const [stats, setStats] = useState<SignalStats>({ active: 0, latest_count: 0 });
  const [loading, setLoading] = useState(false);
  const [historyDays, setHistoryDays] = useState(7);

  const load = async () => {
    setLoading(true);
    try {
      if (tab === "active") {
        const res = await api.getActiveSignals();
        setActiveSignals(res.signals || []);
        setStats(res.stats || { active: 0, latest_count: 0 });
      } else {
        const res = await api.getSignalHistory(historyDays);
        setHistorySignals(res.signals || []);
      }
    } catch (err) {
      console.error("load signals failed", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [tab, historyDays]);

  const filtered = useMemo(() => {
    const list = tab === "active" ? activeSignals : historySignals;
    if (filter === "ALL") return list;
    return list.filter(s => s.signal_type === filter);
  }, [tab, activeSignals, historySignals, filter]);

  const premiumCount = filtered.filter(s => s.signal_type === "PREMIUM").length;
  const discountCount = filtered.filter(s => s.signal_type === "DISCOUNT").length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/fund-opportunity" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-warning" />
          <h1 className="text-xl font-semibold tracking-tight">套利信号</h1>
        </div>
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          Z-score 异常检测
        </span>
      </div>

      {/* Stats (only on active tab) */}
      {tab === "active" && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="活跃信号"
            value={stats.active}
            sub={`最新一批 ${stats.latest_count} 个`}
            icon={<Activity className="h-4 w-4" />}
            tone="text-primary"
          />
          <StatCard
            label="溢价信号"
            value={premiumCount}
            sub="申购 → 场内卖出"
            icon={<TrendingUp className="h-4 w-4" />}
            tone="text-danger"
          />
          <StatCard
            label="折价信号"
            value={discountCount}
            sub="场内买入 → 赎回"
            icon={<TrendingDown className="h-4 w-4" />}
            tone="text-success"
          />
          <StatCard
            label="检测基金"
            value={filtered.length}
            sub={`基于 20 日历史分位`}
            icon={<Filter className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Tabs + Controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="inline-flex rounded-lg border bg-muted/50 p-1">
          <button
            onClick={() => setTab("active")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              tab === "active" ? "bg-background shadow" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5" />
              活跃信号
            </span>
          </button>
          <button
            onClick={() => setTab("history")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              tab === "history" ? "bg-background shadow" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              <History className="h-3.5 w-3.5" />
              历史记录
            </span>
          </button>
        </div>

        <div className="inline-flex rounded-lg border bg-muted/50 p-1">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                filter === opt.value ? "bg-background shadow" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {tab === "history" && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">回溯</span>
            <select
              value={historyDays}
              onChange={e => setHistoryDays(Number(e.target.value))}
              className="rounded border bg-background px-2 py-1 text-sm"
            >
              <option value={7}>7 天</option>
              <option value={14}>14 天</option>
              <option value={30}>30 天</option>
              <option value={60}>60 天</option>
            </select>
          </div>
        )}

        <button
          onClick={load}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          刷新
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Activity className="mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">暂无{tab === "active" ? "活跃" : "历史"}信号</p>
          <p className="mt-1 text-xs">系统会在交易时段持续检测折溢价异常</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((s, i) => (
            <SignalRow key={`${s.code}-${s.trade_date}-${i}`} signal={s} />
          ))}
        </div>
      )}
    </div>
  );
}
