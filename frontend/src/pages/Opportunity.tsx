import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Circle, Clock3, Lightbulb, SlidersHorizontal, TrendingDown, TrendingUp } from "lucide-react";
import { api, type DailyRecommendationItem, type Opportunity, type OpportunityCategory } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  buildIntelPath,
  MarketEmptyState,
  MarketErrorState,
  MarketIntelHeader,
  MarketLoadingState,
  normalizeChinaSymbol,
  plainSymbol,
} from "@/components/market/MarketIntelShell";

const REFRESH_MS = 300_000;

type Candidate = Opportunity & {
  categoryId: string;
  categoryLabel: string;
  color: string;
  score: number;
  fit: "morning" | "afternoon" | "watch";
};

function fmtPrice(value: number): string {
  return value >= 1000 ? value.toFixed(0) : value.toFixed(2);
}

function fmtPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function fitFor(item: Opportunity & { categoryId: string }): Candidate["fit"] {
  if (item.categoryId === "event" || item.categoryId === "breakout") return "morning";
  if (item.categoryId === "trend") return "afternoon";
  return "watch";
}

function fitLabel(fit: Candidate["fit"]): string {
  if (fit === "morning") return "9:27 适配";
  if (fit === "afternoon") return "14:30 适配";
  return "观察池";
}

function unselectedReason(item: Candidate): string {
  if (item.change_pct > 7) return "涨幅偏高，等待回踩确认";
  if (item.score < 0.7) return "信号强度不足";
  if (item.fit === "watch") return "反弹类信号需二次确认";
  return "等待每日推荐排序确认";
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function Opportunity() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<OpportunityCategory[]>([]);
  const [dailyItems, setDailyItems] = useState<DailyRecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [symbol, setSymbol] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
  const [fit, setFit] = useState(searchParams.get("fit") ?? "all");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback((silent = false) => {
    if (!silent) setRefreshing(true);
    Promise.all([
      api.listOpportunities(),
      api.listDailyRecommendations({ date: today(), limit: 50 }).catch(() => ({ items: [] as DailyRecommendationItem[] })),
    ])
      .then(([opps, daily]) => {
        setCategories(opps.categories);
        setDailyItems(daily.items ?? []);
        setUpdatedAt(opps.updated_at);
        setError(opps.error ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载候选池失败"))
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setSymbol(plainSymbol(searchParams.get("symbol") ?? ""));
    setFit(searchParams.get("fit") ?? "all");
  }, [searchParams]);

  useEffect(() => {
    setLoading(true);
    fetchData(true);
  }, [fetchData]);

  useEffect(() => {
    intervalRef.current = setInterval(() => fetchData(true), REFRESH_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const applySearch = useCallback(() => {
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (symbol.trim()) next.set("symbol", normalizeChinaSymbol(symbol));
    if (fit !== "all") next.set("fit", fit);
    setSearchParams(next);
  }, [fit, query, setSearchParams, symbol]);

  const dailyMap = useMemo(() => new Map(dailyItems.map((item) => [item.symbol, item])), [dailyItems]);

  const candidates = useMemo<Candidate[]>(() => {
    return categories.flatMap((cat) =>
      cat.opportunities.map((item) => ({
        ...item,
        categoryId: cat.id,
        categoryLabel: cat.label,
        color: cat.color,
        score: item.confidence,
        fit: fitFor({ ...item, categoryId: cat.id }),
      })),
    );
  }, [categories]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sym = plainSymbol(symbol);
    return candidates
      .filter((item) => fit === "all" || item.fit === fit)
      .filter((item) => {
        if (sym && !plainSymbol(item.symbol).includes(sym)) return false;
        if (!q) return true;
        return `${item.name} ${item.symbol} ${item.reason} ${item.categoryLabel}`.toLowerCase().includes(q);
      })
      .sort((a, b) => {
        const aIn = dailyMap.has(a.symbol) ? 1 : 0;
        const bIn = dailyMap.has(b.symbol) ? 1 : 0;
        if (aIn !== bIn) return bIn - aIn;
        return b.score - a.score;
      });
  }, [candidates, dailyMap, fit, query, symbol]);

  return (
    <div className="flex h-full flex-col">
      <MarketIntelHeader
        active="opportunity"
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
          <FilterButton label="全部候选" active={fit === "all"} onClick={() => updateFit("all")} />
          <FilterButton label="9:27 适配" active={fit === "morning"} onClick={() => updateFit("morning")} />
          <FilterButton label="14:30 适配" active={fit === "afternoon"} onClick={() => updateFit("afternoon")} />
          <FilterButton label="观察池" active={fit === "watch"} onClick={() => updateFit("watch")} />
          <span className="ml-auto text-xs text-muted-foreground">当前 {visibleItems.length} 个候选</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <MarketLoadingState label="正在筛选候选池" />
        ) : error ? (
          <MarketErrorState message={error} onRetry={() => fetchData()} />
        ) : visibleItems.length === 0 ? (
          <MarketEmptyState
            icon={Lightbulb}
            title="当前筛选下暂无候选"
            description="放宽关键词或切换推荐时段适配条件后再试。"
          />
        ) : (
          <div className="overflow-hidden rounded-md border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/30 text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">标的</th>
                  <th className="px-3 py-2 text-left font-medium">信号</th>
                  <th className="px-3 py-2 text-left font-medium">推荐时段</th>
                  <th className="px-3 py-2 text-left font-medium">入选状态</th>
                  <th className="px-3 py-2 text-right font-medium">价格/涨跌</th>
                  <th className="px-3 py-2 text-left font-medium">理由</th>
                  <th className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((item) => (
                  <CandidateRow
                    key={`${item.categoryId}-${item.symbol}`}
                    item={item}
                    selected={dailyMap.get(item.symbol)}
                    params={searchParams}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );

  function updateFit(nextFit: string) {
    setFit(nextFit);
    const next = new URLSearchParams(searchParams);
    if (nextFit === "all") next.delete("fit");
    else next.set("fit", nextFit);
    setSearchParams(next);
  }
}

function FilterButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors",
        active ? "border-primary/40 bg-primary/10 text-primary" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <SlidersHorizontal className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

function CandidateRow({
  item,
  selected,
  params,
}: {
  item: Candidate;
  selected?: DailyRecommendationItem;
  params: URLSearchParams;
}) {
  const next = new URLSearchParams(params);
  next.set("symbol", normalizeChinaSymbol(item.symbol));
  if (!next.get("q")) next.set("q", item.name);
  const score = Math.round(item.score * 100);

  return (
    <tr className="border-b last:border-0 hover:bg-muted/25">
      <td className="px-3 py-3">
        <div className="min-w-[140px]">
          <p className="font-medium">{item.name}</p>
          <p className="font-mono text-[10px] text-muted-foreground">{item.symbol}</p>
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="min-w-[120px]">
          <p className="text-xs font-medium">{item.categoryLabel}</p>
          <div className="mt-1 flex items-center gap-2">
            <div className="h-1.5 w-20 rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${score}%` }} />
            </div>
            <span className="text-[10px] text-muted-foreground">{score}</span>
          </div>
        </div>
      </td>
      <td className="px-3 py-3">
        <span className="inline-flex items-center gap-1 rounded bg-muted px-2 py-1 text-[10px] text-muted-foreground">
          <Clock3 className="h-3 w-3" />
          {fitLabel(item.fit)}
        </span>
      </td>
      <td className="px-3 py-3">
        {selected ? (
          <span className="inline-flex items-center gap-1 rounded bg-success/10 px-2 py-1 text-[10px] font-medium text-success">
            <CheckCircle2 className="h-3 w-3" />
            已入选 {selected.slot_label}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded bg-warning/10 px-2 py-1 text-[10px] text-warning">
            <Circle className="h-3 w-3" />
            {unselectedReason(item)}
          </span>
        )}
      </td>
      <td className="px-3 py-3 text-right">
        <p className="font-mono text-xs">¥{fmtPrice(item.price)}</p>
        <p className={cn("text-xs font-medium", item.change_pct >= 0 ? "text-success" : "text-danger")}>
          {item.change_pct >= 0 ? <TrendingUp className="mr-0.5 inline h-3 w-3" /> : <TrendingDown className="mr-0.5 inline h-3 w-3" />}
          {fmtPct(item.change_pct)}
        </p>
      </td>
      <td className="max-w-[360px] px-3 py-3">
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>
      </td>
      <td className="px-3 py-3">
        <div className="flex justify-end gap-2">
          <Link to={buildIntelPath("/logic-chain", next)} className="rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:opacity-90">
            解释
          </Link>
          <Link to={buildIntelPath("/daily-recommendations", next)} className="rounded-md border px-2.5 py-1 text-xs hover:bg-muted">
            推荐
          </Link>
        </div>
      </td>
    </tr>
  );
}
