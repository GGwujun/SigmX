import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Flame, Sparkles, Zap, Circle } from "lucide-react";
import { api, type OpportunityCategory } from "@/lib/api";
import { cn } from "@/lib/utils";

const REFRESH_MS = 300_000; // 5 min

const CAT_ICONS: Record<string, typeof Flame> = {
  breakout: Flame,
  trend: TrendingUp,
  oversold: Sparkles,
  event: Zap,
};

const CAT_COLORS: Record<string, { bg: string; text: string; bar: string }> = {
  red: { bg: "bg-red-500/5 border-red-500/20", text: "text-red-600 dark:text-red-400", bar: "bg-red-500" },
  green: { bg: "bg-green-500/5 border-green-500/20", text: "text-green-600 dark:text-green-400", bar: "bg-green-500" },
  blue: { bg: "bg-blue-500/5 border-blue-500/20", text: "text-blue-600 dark:text-blue-400", bar: "bg-blue-500" },
  amber: { bg: "bg-amber-500/5 border-amber-500/20", text: "text-amber-600 dark:text-amber-400", bar: "bg-amber-500" },
};

function fmtPrice(p: number): string {
  return p >= 1000 ? p.toFixed(0) : p.toFixed(2);
}

function fmtPct(p: number): string {
  return `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`;
}

export function Opportunity() {
  const [categories, setCategories] = useState<OpportunityCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback((silent = false) => {
    if (!silent) setRefreshing(true);
    api.listOpportunities()
      .then((res) => {
        setCategories(res.categories);
        setError(res.error ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, []);

  useEffect(() => { setLoading(true); fetchData(true); }, [fetchData]);
  useEffect(() => {
    intervalRef.current = setInterval(() => fetchData(true), REFRESH_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchData]);

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b shrink-0">
        <div>
          <h1 className="text-lg font-semibold">机会清单</h1>
          <p className="text-xs text-muted-foreground">A股全市场自动扫描 · 四维度发现交易机会</p>
        </div>
        <button onClick={() => fetchData()} disabled={refreshing}
          className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors">
          <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {loading ? (
          <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <AlertTriangle className="w-8 h-8" />
            <p className="text-sm">{error}</p>
            <button onClick={() => fetchData()} className="text-xs text-primary hover:underline">重试</button>
          </div>
        ) : (
          categories.map((cat) => {
            const Icon = CAT_ICONS[cat.id] || Circle;
            const color = CAT_COLORS[cat.color] || CAT_COLORS.green;
            return (
              <section key={cat.id}>
                <div className="flex items-center gap-2 mb-3">
                  <Icon className={cn("w-5 h-5", color.text)} />
                  <h2 className="text-base font-semibold">{cat.label}</h2>
                  <span className="text-xs text-muted-foreground ml-1">{cat.opportunities.length} 个机会</span>
                </div>

                {cat.opportunities.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">暂未发现此类机会</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                    {cat.opportunities.map((opp) => (
                      <div key={opp.symbol} className={cn("border rounded-xl p-4 transition-colors hover:shadow-sm", color.bg)}>
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <p className="font-semibold text-sm">{opp.name}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{opp.symbol}</p>
                          </div>
                          <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full", color.text, color.bg)}>
                            {(opp.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex items-baseline gap-2 mb-2">
                          <span className="text-lg font-bold tabular-nums">¥{fmtPrice(opp.price)}</span>
                          <span className={cn("text-xs font-medium", opp.change_pct >= 0 ? "text-green-500" : "text-red-500")}>
                            {opp.change_pct >= 0 ? <TrendingUp className="w-3 h-3 inline mr-0.5" /> : <TrendingDown className="w-3 h-3 inline mr-0.5" />}
                            {fmtPct(opp.change_pct)}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">{opp.reason}</p>
                        {/* Confidence bar */}
                        <div className="mt-2 h-1 rounded-full bg-muted/50 overflow-hidden">
                          <div className={cn("h-full rounded-full transition-all", color.bar)} style={{ width: `${opp.confidence * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}
