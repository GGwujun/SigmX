import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowRight,
  GitBranch,
  Lightbulb,
  Loader2,
  Newspaper,
  RefreshCw,
  Search,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type MarketStageId = "news" | "events" | "opportunity" | "logic-chain";

const STAGES: Array<{
  id: MarketStageId;
  label: string;
  desc: string;
  path: string;
  icon: LucideIcon;
}> = [
  { id: "news", label: "新闻线索", desc: "发现发生了什么", path: "/news", icon: Newspaper },
  { id: "events", label: "事件雷达", desc: "验证影响强度", path: "/events", icon: TrendingUp },
  { id: "opportunity", label: "机会清单", desc: "沉淀候选标的", path: "/opportunity", icon: Lightbulb },
  { id: "logic-chain", label: "逻辑链", desc: "解释标的逻辑", path: "/logic-chain", icon: GitBranch },
];

export function buildIntelPath(path: string, params: URLSearchParams): string {
  const next = new URLSearchParams();
  const q = params.get("q")?.trim();
  const symbol = params.get("symbol")?.trim();
  const category = params.get("category")?.trim();
  if (q) next.set("q", q);
  if (symbol) next.set("symbol", symbol);
  if (category) next.set("category", category);
  const qs = next.toString();
  return qs ? `${path}?${qs}` : path;
}

export function normalizeChinaSymbol(input: string): string {
  const target = input.trim().toUpperCase();
  if (/^\d{6}\.(SZ|SH)$/.test(target)) return target;
  if (!/^\d{6}$/.test(target)) return target;
  const prefix = target.slice(0, 3);
  return ["000", "001", "002", "003", "004", "159", "300", "301"].includes(prefix)
    ? `${target}.SZ`
    : `${target}.SH`;
}

export function plainSymbol(input: string): string {
  return input.trim().toUpperCase().replace(/\.(SZ|SH)$/, "");
}

export function MarketIntelHeader({
  active,
  query,
  symbol,
  onQueryChange,
  onSymbolChange,
  onSearch,
  onRefresh,
  refreshing,
  updatedAt,
}: {
  active: MarketStageId;
  query: string;
  symbol: string;
  onQueryChange: (value: string) => void;
  onSymbolChange: (value: string) => void;
  onSearch: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  updatedAt?: string;
}) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (symbol.trim()) params.set("symbol", normalizeChinaSymbol(symbol));

  return (
    <div className="border-b bg-card/80">
      <div className="px-4 md:px-6 py-4 space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">市场情报</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              新闻线索到逻辑链的连续研究入口，围绕同一个关键词或标的推进。
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {updatedAt && <span>更新于 {formatUpdatedAt(updatedAt)}</span>}
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={refreshing}
                className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/35 hover:bg-primary/5 hover:text-foreground disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
                刷新
              </button>
            )}
          </div>
        </div>

        <div className="grid gap-2 lg:grid-cols-[1.4fr_0.8fr_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onSearch();
              }}
              placeholder="搜索关键词、行业主题、事件线索"
              className="h-10 w-full rounded-md border bg-background pl-9 pr-3 text-sm outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
            />
          </div>
          <input
            value={symbol}
            onChange={(event) => onSymbolChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSearch();
            }}
            placeholder="标的代码，如 600519"
            className="h-10 rounded-md border bg-background px-3 text-sm outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
          />
          <button
            type="button"
            onClick={onSearch}
            className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            进入研究
          </button>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          {STAGES.map((stage, index) => {
            const Icon = stage.icon;
            const current = stage.id === active;
            return (
              <Link
                key={stage.id}
                to={buildIntelPath(stage.path, params)}
                className={cn(
                  "group flex min-w-[152px] items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors",
                  current
                    ? "border-primary/45 bg-primary/10 text-primary shadow-[inset_0_-2px_0_hsl(var(--primary))]"
                    : "border-border bg-background text-muted-foreground hover:border-primary/25 hover:bg-primary/[0.03] hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{stage.label}</span>
                  <span className="block truncate text-[10px] opacity-75">{stage.desc}</span>
                </span>
                {index < STAGES.length - 1 && (
                  <ArrowRight className="hidden h-3.5 w-3.5 opacity-40 xl:block" />
                )}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function MarketEmptyState({
  icon: Icon = Search,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed bg-muted/10 px-6 py-14 text-center">
      <Icon className="h-10 w-10 text-muted-foreground/35" />
      <div>
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function MarketErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-danger/20 bg-danger/5 px-6 py-14 text-center text-muted-foreground">
      <AlertTriangle className="h-9 w-9 text-danger/70" />
      <p className="text-sm text-foreground">数据加载失败</p>
      <p className="max-w-md text-xs">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function MarketLoadingState({ label = "正在加载市场情报" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-20 text-sm text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" />
      {label}
    </div>
  );
}

export function SymbolActionBar({
  symbol,
  label,
  params,
  className,
}: {
  symbol: string;
  label?: string;
  params?: URLSearchParams;
  className?: string;
}) {
  const next = new URLSearchParams(params);
  const normalized = normalizeChinaSymbol(symbol);
  next.set("symbol", normalized);
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <span className="text-xs text-muted-foreground">{label ?? "下一步"}</span>
      <Link to={buildIntelPath("/news", next)} className="rounded-md border bg-card px-2.5 py-1 text-xs hover:border-primary/35 hover:bg-primary/5">
        看新闻
      </Link>
      <Link to={buildIntelPath("/events", next)} className="rounded-md border bg-card px-2.5 py-1 text-xs hover:border-primary/35 hover:bg-primary/5">
        验事件
      </Link>
      <Link to={buildIntelPath("/opportunity", next)} className="rounded-md border bg-card px-2.5 py-1 text-xs hover:border-primary/35 hover:bg-primary/5">
        查机会
      </Link>
      <Link to={buildIntelPath("/logic-chain", next)} className="rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:opacity-90">
        进逻辑链
      </Link>
    </div>
  );
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
