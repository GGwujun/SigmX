import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Banknote,
  Building2,
  CheckCircle2,
  ChevronDown,
  FileText,
  GitBranch,
  Globe,
  Newspaper,
  Shield,
  Target,
  TrendingUp,
} from "lucide-react";
import { api, type Layer, type LogicChainResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  MarketEmptyState,
  MarketErrorState,
  MarketIntelHeader,
  MarketLoadingState,
  normalizeChinaSymbol,
  plainSymbol,
  SymbolActionBar,
} from "@/components/market/MarketIntelShell";
import { toast } from "sonner";

const ICONS: Record<string, typeof Globe> = {
  globe: Globe,
  building: Building2,
  "file-text": FileText,
  "trending-up": TrendingUp,
  banknote: Banknote,
  newspaper: Newspaper,
  shield: Shield,
};

function fmtPrice(value: number): string {
  return value >= 1000 ? value.toFixed(0) : value.toFixed(2);
}

function fmtPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tone(score: number): "good" | "warn" | "bad" {
  if (score >= 0.6) return "good";
  if (score >= 0.4) return "warn";
  return "bad";
}

function toneClass(value: "good" | "warn" | "bad"): string {
  if (value === "good") return "text-success bg-success/10 border-success/20";
  if (value === "warn") return "text-warning bg-warning/10 border-warning/20";
  return "text-danger bg-danger/10 border-danger/20";
}

export function LogicChain() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [code, setCode] = useState(plainSymbol(searchParams.get("symbol") ?? ""));
  const [result, setResult] = useState<LogicChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["technical", "capital"]));

  const analyze = useCallback(async (input?: string) => {
    const raw = (input || code).trim();
    if (!raw) return;
    const normalized = normalizeChinaSymbol(raw);
    if (!/^\d{6}\.(SZ|SH)$/.test(normalized)) {
      toast.error("请输入有效的 A 股代码");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await api.getLogicChain(normalized);
      setResult(res);
      setCode(plainSymbol(res.code));
      setExpanded(new Set(["technical", "capital"]));
      const next = new URLSearchParams(searchParams);
      next.set("symbol", normalized);
      if (query.trim()) next.set("q", query.trim());
      setSearchParams(next, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "逻辑链生成失败");
    } finally {
      setLoading(false);
    }
  }, [code, query, searchParams, setSearchParams]);

  const applySearch = useCallback(() => {
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (code.trim()) next.set("symbol", normalizeChinaSymbol(code));
    setSearchParams(next);
    analyze(code);
  }, [analyze, code, query, setSearchParams]);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
    setCode(plainSymbol(searchParams.get("symbol") ?? ""));
  }, [searchParams]);

  useEffect(() => {
    const sym = searchParams.get("symbol");
    if (sym) analyze(sym);
    // Only auto-run when the URL symbol changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get("symbol")]);

  const supportLayers = useMemo(() => result?.layers.filter((layer) => layer.score >= 0.55).slice(0, 4) ?? [], [result]);
  const riskLayers = useMemo(() => result?.layers.filter((layer) => layer.score < 0.45).slice(0, 4) ?? [], [result]);

  const flowParams = new URLSearchParams(searchParams);
  if (result?.code) flowParams.set("symbol", result.code);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <MarketIntelHeader
        active="logic-chain"
        query={query}
        symbol={code}
        onQueryChange={setQuery}
        onSymbolChange={setCode}
        onSearch={applySearch}
      />

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <MarketLoadingState label="正在生成推荐解释" />
        ) : error ? (
          <MarketErrorState message={error} onRetry={() => analyze()} />
        ) : !result ? (
          <MarketEmptyState
            icon={GitBranch}
            title="输入标的代码查看推荐解释"
            description="也可以从每日推荐、新闻线索、事件雷达或候选池点击标的进入。"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {["000001", "600519", "300750"].map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => analyze(item)}
                    className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
                  >
                    {item}
                  </button>
                ))}
              </div>
            }
          />
        ) : (
          <div className="mx-auto grid max-w-7xl gap-4 xl:grid-cols-[1fr_320px]">
            <main className="space-y-4">
              <RecommendationSummary result={result} context={query} />

              <section className="grid gap-4 lg:grid-cols-2">
                <EvidencePanel title="支撑证据" icon={CheckCircle2} layers={supportLayers} empty="暂无明显支撑证据，建议降级为观察。" />
                <EvidencePanel title="反证风险" icon={AlertTriangle} layers={riskLayers} empty="当前没有显著反证，但仍需关注价格与量能失效条件。" risk />
              </section>

              <section className="rounded-md border bg-card p-4">
                <div className="mb-3 flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold">完整逻辑层</h3>
                </div>
                <div className="space-y-2">
                  {result.layers.map((layer) => (
                    <LayerAccordion
                      key={layer.id}
                      layer={layer}
                      open={expanded.has(layer.id)}
                      onToggle={() => setExpanded((prev) => {
                        const next = new Set(prev);
                        if (next.has(layer.id)) next.delete(layer.id);
                        else next.add(layer.id);
                        return next;
                      })}
                    />
                  ))}
                </div>
              </section>
            </main>

            <aside className="space-y-4">
              <section className="rounded-md border bg-card p-4">
                <div className="mb-3 flex items-center gap-2">
                  <Target className="h-4 w-4 text-primary" />
                  <p className="text-sm font-semibold">推荐后动作</p>
                </div>
                <div className="space-y-2">
                  <Link to="/daily-recommendations" className="block rounded-md bg-primary px-3 py-2 text-center text-xs font-medium text-primary-foreground hover:opacity-90">
                    回到每日推荐
                  </Link>
                  <Link to={`/opportunity?symbol=${encodeURIComponent(result.code)}`} className="block rounded-md border px-3 py-2 text-center text-xs hover:bg-muted">
                    查看候选池状态
                  </Link>
                  <Link to="/alpha-forge" className="block rounded-md border px-3 py-2 text-center text-xs hover:bg-muted">
                    生成 AlphaForge 报告
                  </Link>
                </div>
              </section>

              <section className="rounded-md border bg-card p-4">
                <p className="text-sm font-semibold">失效条件</p>
                <div className="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
                  <p>跌破止损位 ¥{fmtPrice(result.decision.stop_loss)} 后，推荐假设需要降级。</p>
                  <p>若板块同步转弱或量能萎缩，趋势/突破证据不再充分。</p>
                  <p>若 T+1 未延续且候选池评分下降，应从推荐转为观察。</p>
                </div>
              </section>

              <section className="rounded-md border bg-card p-4">
                <p className="text-sm font-semibold">反查证据</p>
                <SymbolActionBar symbol={result.code} params={flowParams} className="mt-3" />
              </section>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}

function RecommendationSummary({ result, context }: { result: LogicChainResponse; context: string }) {
  const decisionTone = tone(result.decision.score);
  const thesis =
    result.decision.score >= 0.6
      ? "当前交易假设成立，适合作为推荐标的继续跟踪。"
      : result.decision.score >= 0.4
        ? "当前证据不够一致，适合作为观察标的等待确认。"
        : "当前反证较多，不适合作为主动推荐标的。";

  return (
    <section className="rounded-md border bg-card p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{result.name}</h2>
            <span className="font-mono text-sm text-muted-foreground">{result.code}</span>
            {context && <span className="rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">上下文：{context}</span>}
          </div>
          <p className="mt-2 text-sm leading-relaxed">{thesis}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            逻辑链用于解释推荐假设，不替代仓位纪律；正式结论应结合回测表现和后续跟踪。
          </p>
        </div>
        <div className="grid min-w-[320px] grid-cols-2 gap-2">
          <Metric label="当前价" value={`¥${fmtPrice(result.price)}`} tone={result.change_pct >= 0 ? "up" : "down"} />
          <Metric label="涨跌幅" value={fmtPct(result.change_pct)} tone={result.change_pct >= 0 ? "up" : "down"} />
          <Metric label="综合评分" value={result.decision.score.toFixed(2)} />
          <Metric label="建议动作" value={`${result.decision.signal} ${result.decision.action}`} className={toneClass(decisionTone)} />
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <Metric label="建议仓位" value={`${result.decision.position_pct}%`} />
        <Metric label="止损位" value={`¥${fmtPrice(result.decision.stop_loss)}`} tone="down" />
        <Metric label="止盈位" value={`¥${fmtPrice(result.decision.take_profit)}`} tone="up" />
      </div>
    </section>
  );
}

function EvidencePanel({
  title,
  icon: Icon,
  layers,
  empty,
  risk,
}: {
  title: string;
  icon: typeof CheckCircle2;
  layers: Layer[];
  empty: string;
  risk?: boolean;
}) {
  return (
    <section className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className={cn("h-4 w-4", risk ? "text-warning" : "text-success")} />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {layers.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-xs leading-relaxed text-muted-foreground">{empty}</p>
      ) : (
        <div className="space-y-2">
          {layers.map((layer) => (
            <div key={layer.id} className="rounded-md bg-muted/35 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium">{layer.label}</span>
                <span className={cn("text-xs font-semibold tabular-nums", toneClass(tone(layer.score)))}>{Math.round(layer.score * 100)} 分</span>
              </div>
              <div className="mt-2 space-y-1">
                {layer.items.slice(0, 3).map((item) => (
                  <div key={`${layer.id}-${item.label}`} className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="text-right font-medium">{item.value} {item.signal}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function LayerAccordion({ layer, open, onToggle }: { layer: Layer; open: boolean; onToggle: () => void }) {
  const Icon = ICONS[layer.icon] || Globe;
  const layerTone = tone(layer.score);
  return (
    <div className="overflow-hidden rounded-md border bg-background">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/30"
      >
        <Icon className={cn("h-4 w-4", layerTone === "good" && "text-success", layerTone === "warn" && "text-warning", layerTone === "bad" && "text-danger")} />
        <span className="flex-1 text-sm font-medium">{layer.label}</span>
        <span className="text-xs">{layer.signal}</span>
        <span className="text-xs text-muted-foreground">{Math.round(layer.score * 100)} 分</span>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t px-4 py-3">
          <div className="grid gap-2 sm:grid-cols-2">
            {layer.items.map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-2 rounded-md bg-muted/30 px-3 py-2">
                <span className="text-xs text-muted-foreground">{item.label}</span>
                <span className="flex items-center gap-1.5 text-xs font-medium">
                  {item.value}
                  <span>{item.signal}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
  className,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
  className?: string;
}) {
  return (
    <div className={cn("rounded-md border bg-background px-3 py-2", className)}>
      <p className={cn("text-base font-semibold tabular-nums", tone === "up" && "text-success", tone === "down" && "text-danger")}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}
