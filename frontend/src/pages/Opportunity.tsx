import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Circle,
  Flame,
  Lightbulb,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api, type Opportunity, type OpportunityCategory } from "@/lib/api";
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

const CAT_ICONS: Record<string, typeof Flame> = {
  breakout: Flame,
  trend: TrendingUp,
  oversold: Sparkles,
  event: Zap,
};

const CAT_COLORS: Record<string, { bg: string; text: string; bar: string }> = {
  red: { bg: "bg-danger/5 border-danger/20", text: "text-danger", bar: "bg-danger" },
  green: { bg: "bg-success/5 border-success/20", text: "text-success", bar: "bg-success" },
  blue: { bg: "bg-info/5 border-info/20", text: "text-info", bar: "bg-info" },
  amber: { bg: "bg-warning/5 border-warning/20", text: "text-warning", bar: "bg-warning" },
};

type SortKey = "confidence" | "change" | "name";

function fmtPrice(value: number): string {
  return value >= 1000 ? value.toFixed(0) : value.toFixed(2);
}

function fmtPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function Opportunity() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<OpportunityCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [symbol, setSymbol] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
  const [category, setCategory] = useState(searchParams.get("category") ?? "all");
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback((silent = false) => {
    if (!silent) setRefreshing(true);
    api.listOpportunities()
      .then((res) => {
        setCategories(res.categories);
        setUpdatedAt(res.updated_at);
        setError(res.error ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载机会清单失败"))
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setSymbol(plainSymbol(searchParams.get("symbol") ?? ""));
    setCategory(searchParams.get("category") ?? "all");
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
    if (category !== "all") next.set("category", category);
    setSearchParams(next);
  }, [category, query, setSearchParams, symbol]);

  const allItems = useMemo(() => {
    return categories.flatMap((cat) => cat.opportunities.map((item) => ({ ...item, categoryLabel: cat.label, categoryId: cat.id, color: cat.color })));
  }, [categories]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sym = plainSymbol(symbol);
    return allItems
      .filter((item) => category === "all" || item.categoryId === category)
      .filter((item) => {
        if (sym && !plainSymbol(item.symbol).includes(sym)) return false;
        if (!q) return true;
        return `${item.name} ${item.symbol} ${item.reason} ${item.categoryLabel}`.toLowerCase().includes(q);
      })
      .sort((a, b) => {
        if (sortKey === "change") return b.change_pct - a.change_pct;
        if (sortKey === "name") return a.name.localeCompare(b.name, "zh-CN");
        return b.confidence - a.confidence;
      });
  }, [allItems, category, query, sortKey, symbol]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
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
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              const next = new URLSearchParams(searchParams);
              if (event.target.value === "all") next.delete("category");
              else next.set("category", event.target.value);
              setSearchParams(next);
            }}
            className="h-9 rounded-md border bg-background px-3 text-xs outline-none focus:ring-2 focus:ring-primary/15"
          >
            <option value="all">全部机会</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>{cat.label}</option>
            ))}
          </select>
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value as SortKey)}
            className="h-9 rounded-md border bg-background px-3 text-xs outline-none focus:ring-2 focus:ring-primary/15"
          >
            <option value="confidence">按置信度排序</option>
            <option value="change">按涨跌幅排序</option>
            <option value="name">按名称排序</option>
          </select>
          <span className="text-xs text-muted-foreground">当前 {visibleItems.length} 个候选机会</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <MarketLoadingState label="正在扫描候选机会" />
        ) : error ? (
          <MarketErrorState message={error} onRetry={() => fetchData()} />
        ) : visibleItems.length === 0 ? (
          <MarketEmptyState
            icon={Lightbulb}
            title="当前筛选下暂无候选机会"
            description="可以放宽分类或关键词，也可以先去新闻线索里寻找新的主题。"
            action={
              <Link to={buildIntelPath("/news", searchParams)} className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted">
                查看新闻线索
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleItems.map((item) => (
              <OpportunityCard key={`${item.categoryId}-${item.symbol}`} item={item} params={searchParams} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function OpportunityCard({
  item,
  params,
}: {
  item: Opportunity & { categoryLabel: string; categoryId: string; color: string };
  params: URLSearchParams;
}) {
  const color = CAT_COLORS[item.color] || CAT_COLORS.green;
  const Icon = CAT_ICONS[item.categoryId] || Circle;
  const next = new URLSearchParams(params);
  next.set("symbol", normalizeChinaSymbol(item.symbol));
  if (!next.get("q")) next.set("q", item.name);

  return (
    <article className={cn("flex min-h-[238px] flex-col rounded-md border bg-card p-4 transition-colors hover:border-primary/35 hover:bg-primary/[0.03]", color.bg)}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Icon className={cn("h-4 w-4", color.text)} />
            <p className="truncate text-sm font-semibold">{item.name}</p>
          </div>
          <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{item.symbol}</p>
        </div>
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", color.text, "bg-background/70")}>
          {(item.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-xl font-bold tabular-nums">¥{fmtPrice(item.price)}</span>
        <span className={cn("text-xs font-medium", item.change_pct >= 0 ? "text-success" : "text-danger")}>
          {item.change_pct >= 0 ? <TrendingUp className="mr-0.5 inline h-3 w-3" /> : <TrendingDown className="mr-0.5 inline h-3 w-3" />}
          {fmtPct(item.change_pct)}
        </span>
      </div>

      <p className="line-clamp-3 flex-1 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>

      <div className="mt-3 h-1 rounded-full bg-background/60">
        <div className={cn("h-full rounded-full", color.bar)} style={{ width: `${item.confidence * 100}%` }} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={buildIntelPath("/news", next)} className="rounded-md border bg-background/70 px-2.5 py-1 text-xs hover:bg-muted">
          看新闻
        </Link>
        <Link to={buildIntelPath("/events", next)} className="rounded-md border bg-background/70 px-2.5 py-1 text-xs hover:bg-muted">
          验事件
        </Link>
        <Link to={buildIntelPath("/logic-chain", next)} className="rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:opacity-90">
          进逻辑链
        </Link>
      </div>
    </article>
  );
}
