import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, CalendarDays, Loader2, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { api, type DailyRecommendationBacktestResponse, type DailyRecommendationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

function fmtPct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function retTone(value?: number | null): string {
  if (value === undefined || value === null) return "text-muted-foreground";
  if (value > 0) return "text-success";
  if (value < 0) return "text-danger";
  return "text-muted-foreground";
}

function slotLabel(slot: string): string {
  if (slot === "morning") return "9:27";
  if (slot === "afternoon") return "14:30";
  return "手动";
}

export function RecommendationHistory() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<DailyRecommendationBacktestResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getDailyRecommendationBacktest(days));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "加载推荐历史失败");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <header className="shrink-0 border-b bg-card/60 px-4 py-4 md:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold tracking-tight">推荐历史</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">看系统过去推荐的 T+0/T+1/T+3/T+5 表现和分时段胜率。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {[7, 30, 90].map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setDays(item)}
                className={cn(
                  "h-9 rounded-md border px-3 text-xs transition-colors",
                  days === item ? "border-primary/40 bg-primary/10 text-primary" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                近 {item} 天
              </button>
            ))}
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              刷新
            </button>
            <Link to="/daily-recommendations" className="h-9 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90">
              今日推荐
            </Link>
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在加载历史表现
          </div>
        ) : !data ? (
          <Empty />
        ) : (
          <div className="mx-auto max-w-7xl space-y-4">
            <Summary data={data} />
            <HistoryTable items={items} />
          </div>
        )}
      </main>
    </div>
  );
}

function Empty() {
  return (
    <div className="mx-auto flex min-h-[360px] max-w-3xl flex-col items-center justify-center rounded-md border border-dashed bg-muted/10 px-6 text-center">
      <CalendarDays className="h-10 w-10 text-muted-foreground/40" />
      <p className="mt-3 text-sm font-medium">暂无推荐历史</p>
      <p className="mt-1 text-xs text-muted-foreground">生成过每日推荐后，这里会自动累积表现。</p>
    </div>
  );
}

function Summary({ data }: { data: DailyRecommendationBacktestResponse }) {
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <Metric label="推荐数" value={`${data.summary.count}`} />
      <Metric label="T+1样本" value={`${data.summary.t1_count}`} />
      <Metric label="T+1胜率" value={data.summary.t1_win_rate === null ? "-" : `${data.summary.t1_win_rate}%`} />
      <Metric label="T+1均值" value={fmtPct(data.summary.t1_avg_return)} tone={retTone(data.summary.t1_avg_return)} />
      {data.by_slot.map((row) => (
        <div key={row.slot} className="rounded-md border bg-card p-4 md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-semibold">{slotLabel(row.slot)} 推荐</p>
            <span className="text-xs text-muted-foreground">{row.count} 条</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="T+1胜率" value={row.t1_win_rate === null ? "-" : `${row.t1_win_rate}%`} compact />
            <Metric label="T+1均值" value={fmtPct(row.t1_avg_return)} tone={retTone(row.t1_avg_return)} compact />
          </div>
        </div>
      ))}
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

function HistoryTable({ items }: { items: DailyRecommendationItem[] }) {
  if (!items.length) return <Empty />;
  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">日期</th>
            <th className="px-3 py-2 text-left font-medium">时段</th>
            <th className="px-3 py-2 text-left font-medium">标的</th>
            <th className="px-3 py-2 text-left font-medium">策略</th>
            <th className="px-3 py-2 text-right font-medium">T+0</th>
            <th className="px-3 py-2 text-right font-medium">T+1</th>
            <th className="px-3 py-2 text-right font-medium">T+3</th>
            <th className="px-3 py-2 text-right font-medium">T+5</th>
            <th className="px-3 py-2 text-right font-medium">最新</th>
            <th className="px-3 py-2 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b last:border-0 hover:bg-muted/25">
              <td className="px-3 py-3 text-xs text-muted-foreground">{item.date}</td>
              <td className="px-3 py-3 text-xs">{slotLabel(item.slot)}</td>
              <td className="px-3 py-3">
                <p className="text-xs font-medium">{item.name}</p>
                <p className="font-mono text-[10px] text-muted-foreground">{item.symbol}</p>
              </td>
              <td className="px-3 py-3 text-xs text-muted-foreground">{item.strategy}</td>
              <ReturnCell value={item.performance.t0?.return_pct} />
              <ReturnCell value={item.performance.t1?.return_pct} />
              <ReturnCell value={item.performance.t3?.return_pct} />
              <ReturnCell value={item.performance.t5?.return_pct} />
              <ReturnCell value={item.performance.latest_return_pct} icon />
              <td className="px-3 py-3 text-right">
                <Link to={`/logic-chain?symbol=${encodeURIComponent(item.symbol)}&q=${encodeURIComponent(item.reason || item.name)}`} className="rounded-md border px-2.5 py-1 text-xs hover:bg-muted">
                  复盘
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
