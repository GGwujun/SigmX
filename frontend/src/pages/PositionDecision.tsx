import { useState, useEffect, useCallback, useRef } from "react";
import {
  TrendingUp, TrendingDown, AlertTriangle, Loader2, RefreshCw, X,
  Plus, Trash2, Target, Circle, Minus, Wallet, ChevronDown, Sparkles,
} from "lucide-react";
import { api, type PositionSignal, type AnalysisDimension } from "@/lib/api";
import { cn } from "@/lib/utils";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Position {
  symbol: string;
  cost: number;
  shares: number;
  date: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_MS = 120_000;
const LS_KEY = "vibe-position-watchlist";

const DECISION_COLORS: Record<string, string> = {
  strong_buy: "text-emerald-600 bg-emerald-500/10 border-emerald-500/20",
  buy: "text-green-600 bg-green-500/10 border-green-500/20",
  hold: "text-amber-600 bg-amber-500/10 border-amber-500/20",
  sell: "text-red-600 bg-red-500/10 border-red-500/20",
  strong_sell: "text-rose-600 bg-rose-500/10 border-rose-500/20",
};

const DIRECTION_ICONS: Record<string, typeof TrendingUp> = {
  up: TrendingUp,
  down: TrendingDown,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPrice(p: number): string {
  return p >= 1000 ? p.toFixed(0) : p.toFixed(3);
}

function fmtPct(p: number): string {
  const s = p >= 0 ? "+" : "";
  return `${s}${p.toFixed(2)}%`;
}

function fmtPnL(val: number): string {
  const s = val >= 0 ? "+" : "";
  return `${s}${val.toFixed(0)}`;
}

function fmtMoney(val: number): string {
  const sign = val < 0 ? "-" : "";
  const abs = Math.abs(val);
  if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(1)}万`;
  return `${sign}${abs.toFixed(0)}`;
}

function loadPositions(): Position[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr) && arr.length) return arr;
    }
  } catch { /* ignore */ }
  return [];
}

function savePositions(list: Position[]): void {
  localStorage.setItem(LS_KEY, JSON.stringify(list));
  // Fire-and-forget server persist (don't block UI)
  api.saveWatchlist(list).catch(() => {});
}

// ---------------------------------------------------------------------------
// Radar chart
// ---------------------------------------------------------------------------

function RadarChart({ signal, dark }: { signal: PositionSignal; dark: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const theme = getChartTheme();
    const chart = echarts.init(ref.current);

    // Use dimensions array (v2) if available, fall back to legacy 4-axis
    const dims = signal.dimensions;
    const indicators = dims?.length
      ? dims.map((d) => ({ name: d.label.length > 3 ? d.label.slice(0, 3) : d.label, max: 1 }))
      : [
          { name: "趋势", max: 1 },
          { name: "技术形态", max: 1 },
          { name: "动量", max: 1 },
          { name: "事件情绪", max: 1 },
        ];
    const values = dims?.length
      ? dims.map((d) => d.score)
      : [signal.trend.score, signal.technical.score, signal.momentum.score, signal.events.score];

    chart.setOption({
      tooltip: { trigger: "item" },
      legend: { show: false },
      radar: {
        center: ["50%", "50%"],
        radius: dims?.length ? "65%" : "70%",
        indicator: indicators,
        shape: "polygon",
        axisName: { color: theme.textColor, fontSize: dims?.length ? 9 : 10 },
        splitArea: { areaStyle: { color: ["transparent"] } },
        splitLine: { lineStyle: { color: theme.gridColor } },
        axisLine: { lineStyle: { color: theme.axisColor } },
      },
      series: [{
        type: "radar",
        data: [{ value: values, name: "信号", areaStyle: { color: theme.infoColor + "33" }, lineStyle: { color: theme.infoColor } }],
        symbol: "circle",
        symbolSize: dims?.length ? 3 : 4,
      }],
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.dispose(); };
  }, [signal, dark]);

  return <div ref={ref} className="w-full h-[200px]" />;
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Score bar
// ---------------------------------------------------------------------------

function ScoreBar({ score, height = 4 }: { score: number; height?: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.60 ? "bg-green-500" : score >= 0.40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 bg-muted rounded-full" style={{ height }}>
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-muted-foreground w-8 tabular-nums text-right">{pct}分</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SL/TP indicator
// ---------------------------------------------------------------------------

function SLTPIndicator({ price, sl, tp, rr }: { price: number; sl?: number | null; tp?: number | null; rr?: number | null }) {
  if (!sl || !tp) return null;
  const range = tp - sl;
  if (range <= 0) return null;
  const pct = ((price - sl) / range) * 100;
  return (
    <div className="bg-muted/40 rounded-lg p-3 space-y-1.5">
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>止损 ¥{fmtPrice(sl)}</span>
        <span>止盈 ¥{fmtPrice(tp)}</span>
      </div>
      <div className="relative h-2 bg-muted rounded-full">
        <div className="absolute left-0 top-0 h-full w-[40%] rounded-l-full bg-red-500/20" />
        <div className="absolute right-0 top-0 h-full w-[30%] rounded-r-full bg-green-500/20" />
        <div
          className="absolute top-0 h-full w-2.5 -ml-1 bg-white border-2 border-primary rounded-full shadow"
          style={{ left: `${Math.max(2, Math.min(98, pct))}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px]">
        <span className="text-muted-foreground">盈亏比 {rr ?? "—"}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dimension Accordion
// ---------------------------------------------------------------------------

const DIM_ICONS: Record<string, string> = {
  macro: "🌐", industry: "🏢", fundamental: "📊", technical: "📈",
  capital: "💰", risk: "🛡️", events: "📰",
};

function DimensionAccordion({
  dim, defaultOpen,
}: {
  dim: AnalysisDimension;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const score = dim.score;
  const emoji = DIM_ICONS[dim.id] || "📌";

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-muted/50 transition-colors text-left"
      >
        <span className="text-sm">{emoji}</span>
        <span className="text-xs font-medium flex-1">{dim.label}</span>
        <span className={cn("text-xs tabular-nums", score >= 0.60 ? "text-green-500" : score >= 0.40 ? "text-amber-500" : "text-red-500")}>
          {Math.round(score * 100)}分
        </span>
        <span className="text-[10px]">{dim.signal}</span>
        <ChevronDown className={cn("w-3.5 h-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1.5">
          {dim.summary && (
            <p className="text-[10px] text-muted-foreground">{dim.summary}</p>
          )}
          {dim.items.map((item, idx) => (
            <div key={idx} className="flex justify-between items-center text-xs">
              <span className="text-muted-foreground">{item.label}</span>
              <span className="font-medium flex items-center gap-1">
                {item.value}
                <span className="text-[10px]">{item.signal}</span>
              </span>
            </div>
          ))}
          <ScoreBar score={score} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function DetailPanel({
  signal, position, onClose, dark,
  aiLoading, aiContent, aiStreaming, onAiAnalyze,
}: {
  signal: PositionSignal;
  position?: Position;
  onClose: () => void;
  dark: boolean;
  aiLoading: boolean;
  aiContent: string | null;
  aiStreaming: string;
  onAiAnalyze: () => void;
}) {
  const posPnL = position ? (signal.price - position.cost) * position.shares : 0;
  const posPct = position && position.cost > 0 ? ((signal.price - position.cost) / position.cost * 100) : 0;
  const totalValue = position ? signal.price * position.shares : 0;
  const dims = signal.dimensions;

  return (
    <div className="border rounded-xl p-4 bg-card space-y-3 overflow-y-auto max-h-full">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-sm">{signal.name}</h3>
          <p className="text-[10px] text-muted-foreground font-mono">{signal.symbol}</p>
        </div>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-muted" aria-label="关闭">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Price & P&L */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-muted/40 rounded-lg p-2.5">
          <p className="text-[10px] text-muted-foreground">现价</p>
          <p className="text-lg font-bold tabular-nums">¥{fmtPrice(signal.price)}</p>
          <p className={cn("text-[10px] mt-0.5", signal.change_pct >= 0 ? "text-green-500" : "text-red-500")}>
            {fmtPct(signal.change_pct)}
          </p>
        </div>
        {position && position.shares > 0 ? (
          <div className={cn("rounded-lg p-2.5", posPnL >= 0 ? "bg-green-500/10" : "bg-red-500/10")}>
            <p className="text-[10px] text-muted-foreground">持仓盈亏</p>
            <p className={cn("text-lg font-bold tabular-nums", posPnL >= 0 ? "text-green-500" : "text-red-500")}>
              {fmtPnL(posPnL)}
            </p>
            <p className={cn("text-[10px] mt-0.5", posPct >= 0 ? "text-green-500" : "text-red-500")}>
              {fmtPct(posPct)}
            </p>
          </div>
        ) : (
          <div className="bg-muted/40 rounded-lg p-2.5 flex items-center justify-center">
            <p className="text-[10px] text-muted-foreground">暂无持仓</p>
          </div>
        )}
      </div>

      {/* Position info */}
      {position && (position.shares > 0 || position.cost > 0) && (
        <div className="grid grid-cols-3 gap-1.5 text-[10px] bg-muted/40 rounded-lg p-2.5">
          <div><span className="text-muted-foreground">成本</span><p className="font-medium">¥{fmtPrice(position.cost)}</p></div>
          <div><span className="text-muted-foreground">持仓</span><p className="font-medium">{position.shares}股</p></div>
          <div><span className="text-muted-foreground">市值</span><p className="font-medium">{fmtMoney(totalValue)}</p></div>
        </div>
      )}

      {/* Decision badge */}
      <div className={cn("inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-sm font-bold", DECISION_COLORS[signal.decision] || DECISION_COLORS.hold)}>
        <Target className="w-4 h-4" />
        {signal.decision_label}
        <span className="text-[10px] font-normal opacity-60 ml-1">
          评分 {signal.overall_score.toFixed(2)} · {
            signal.confidence === "high" ? "高置信" : signal.confidence === "medium" ? "中置信" : "低置信"
          }
        </span>
      </div>

      {/* SL/TP */}
      <SLTPIndicator
        price={signal.price}
        sl={signal.stop_loss}
        tp={signal.take_profit}
        rr={signal.risk_reward}
      />

      {/* AI Analysis */}
      {aiContent ? (
        <div className={cn(
          "rounded-lg p-3 space-y-1.5",
          aiContent.includes("拦截") || aiContent.includes("失败") || aiContent.includes("出错")
            ? "bg-red-500/5 border border-red-500/10"
            : "bg-primary/5 border border-primary/10"
        )}>
          <div className={cn("flex items-center gap-1.5 text-[10px]",
            aiContent.includes("拦截") || aiContent.includes("失败") || aiContent.includes("出错")
              ? "text-red-500/70"
              : "text-primary/70"
          )}>
            <Sparkles className="w-3 h-3" />
            AI 深度分析
          </div>
          <p className="text-xs leading-relaxed whitespace-pre-wrap">{aiContent}</p>
          <button onClick={onAiAnalyze} disabled={aiLoading}
            className="text-[10px] text-primary/60 hover:text-primary underline">
            {aiLoading ? "分析中..." : "重新分析"}
          </button>
        </div>
      ) : aiLoading ? (
        <div className="bg-primary/5 border border-primary/10 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-2 text-[10px] text-primary/70">
            <Loader2 className="w-3 h-3 animate-spin" />
            AI 正在分析中...
          </div>
          {aiStreaming ? (
            <p className="text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">{aiStreaming}</p>
          ) : (
            <div className="space-y-1.5">
              <div className="h-2 bg-primary/10 rounded animate-pulse" style={{ width: "90%" }} />
              <div className="h-2 bg-primary/10 rounded animate-pulse" style={{ width: "70%" }} />
              <div className="h-2 bg-primary/10 rounded animate-pulse" style={{ width: "80%" }} />
            </div>
          )}
        </div>
      ) : (
        <button onClick={onAiAnalyze} disabled={aiLoading}
          className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-dashed border-primary/30 text-[10px] text-primary/70 hover:bg-primary/5 transition-colors">
          <Sparkles className="w-3 h-3" />
          AI 深度分析
        </button>
      )}

      {/* Radar */}
      <div>
        <h4 className="text-[10px] font-medium text-muted-foreground mb-1">信号雷达</h4>
        <RadarChart signal={signal} dark={dark} />
      </div>

      {/* Dimension accordions */}
      <div className="space-y-1.5">
        <h4 className="text-[10px] font-medium text-muted-foreground px-1">维度分析</h4>
        {dims?.length ? (
          dims.map((dim) => (
            <DimensionAccordion key={dim.id} dim={dim} defaultOpen={dim.id === "technical"} />
          ))
        ) : (
          /* Legacy fallback */
          <div className="bg-muted/40 rounded-lg p-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-muted-foreground">趋势</span>
              <p className="font-medium">{signal.trend.ma_pattern}</p>
            </div>
            <div>
              <span className="text-muted-foreground">技术形态</span>
              <p className="font-medium">{signal.technical.patterns.join("、")}</p>
            </div>
            <div>
              <span className="text-muted-foreground">RSI / MACD</span>
              <p className="font-medium">RSI {signal.momentum.rsi} · {signal.momentum.macd_signal}</p>
            </div>
            <div>
              <span className="text-muted-foreground">量比</span>
              <p className="font-medium">{signal.momentum.vol_ratio}x</p>
            </div>
            <div>
              <span className="text-muted-foreground">事件</span>
              <p className="font-medium">{signal.events.relevant_count}条 · {signal.events.sentiment}</p>
            </div>
            <div>
              <span className="text-muted-foreground">决策</span>
              <p className={cn("font-bold", signal.decision === "buy" || signal.decision === "strong_buy" ? "text-green-500" : signal.decision === "sell" || signal.decision === "strong_sell" ? "text-red-500" : "text-amber-500")}>
                {signal.decision_label}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal table
// ---------------------------------------------------------------------------

function SignalTable({
  signals, positions, selected, onSelect,
}: {
  signals: PositionSignal[];
  positions: Position[];
  selected: string | null;
  onSelect: (s: PositionSignal) => void;
  dark: boolean;
}) {
  const th = "px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground whitespace-nowrap";

  const posMap = new Map(positions.map((p) => [p.symbol, p]));

  // Extract best fundamental metric for quick column display
  const getFundQuick = (s: PositionSignal): string => {
    const dim = s.dimensions?.find((d) => d.id === "fundamental");
    if (!dim?.items?.length) return "—";
    // Prefer ROE as most informative single metric
    const roe = dim.items.find((i) => i.label.includes("ROE"));
    if (roe) return roe.value;
    const pe = dim.items.find((i) => i.label.includes("PE") || i.label.includes("市盈"));
    if (pe) return pe.value;
    return dim.items[0]?.value || "—";
  };

  const getFundColor = (s: PositionSignal): string => {
    const dim = s.dimensions?.find((d) => d.id === "fundamental");
    if (!dim) return "text-muted-foreground";
    if (dim.score >= 0.60) return "text-green-500";
    if (dim.score >= 0.40) return "text-amber-500";
    return "text-red-400";
  };

  // Alpha quick summary for table column
  const getAlphaQuick = (s: PositionSignal): string => {
    const dim = s.dimensions?.find((d) => d.id === "alphas");
    if (!dim?.items?.length) return "—";
    // Count bullish/bearish from the items
    const bullish = dim.items.filter((i) => i.signal === "✅" && i.label.startsWith("  ")).length;
    const bearish = dim.items.filter((i) => i.signal === "🔴" && i.label.startsWith("  ")).length;
    if (!bullish && !bearish) return dim.score >= 0.55 ? "偏强" : dim.score <= 0.45 ? "偏弱" : "中性";
    return `${bullish}多${bearish}空`;
  };

  const getAlphaColor = (s: PositionSignal): string => {
    const dim = s.dimensions?.find((d) => d.id === "alphas");
    if (!dim) return "text-muted-foreground";
    if (dim.score >= 0.60) return "text-green-500";
    if (dim.score >= 0.40) return "text-amber-500";
    return "text-red-400";
  };

  if (!signals.length) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">
        暂无分析数据，请先在左侧添加自选股
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className={th}>名称</th>
            <th className={th}>代码</th>
            <th className={th + " text-right"}>现价</th>
            <th className={th + " text-right"}>涨跌</th>
            <th className={th + " text-right"}>成本</th>
            <th className={th + " text-right"}>盈亏</th>
            <th className={th}>基本面</th>
            <th className={th}>Alpha</th>
            <th className={th}>技术面</th>
            <th className={th + " text-center"}>决策</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => {
            const sel = s.symbol === selected;
            const DirIcon = DIRECTION_ICONS[s.trend.direction] || Minus;
            const pos = posMap.get(s.symbol);
            const pnl = pos && pos.shares > 0 ? (s.price - pos.cost) * pos.shares : 0;
            const pnlPct = pos && pos.cost > 0 ? ((s.price - pos.cost) / pos.cost * 100) : 0;
            const hasDim = s.dimensions?.length;
            const techDim = hasDim ? s.dimensions!.find((d) => d.id === "technical") : null;

            return (
              <tr
                key={s.symbol}
                onClick={() => onSelect(s)}
                className={cn(
                  "border-b last:border-0 cursor-pointer transition-colors hover:bg-muted/50",
                  sel && "bg-primary/5 hover:bg-primary/10",
                )}
              >
                <td className="px-2.5 py-2 text-xs font-medium">{s.name}</td>
                <td className="px-2.5 py-2 font-mono text-[10px] text-muted-foreground">{s.symbol}</td>
                <td className="px-2.5 py-2 text-xs tabular-nums text-right font-medium">
                  ¥{fmtPrice(s.price)}
                </td>
                <td className={cn("px-2.5 py-2 text-xs tabular-nums text-right font-medium", s.change_pct >= 0 ? "text-green-500" : "text-red-500")}>
                  {fmtPct(s.change_pct)}
                </td>
                <td className="px-2.5 py-2 text-xs tabular-nums text-right text-muted-foreground">
                  {pos && pos.cost > 0 ? `¥${fmtPrice(pos.cost)}` : "—"}
                </td>
                <td className="px-2.5 py-2 text-xs tabular-nums text-right">
                  {pos && pos.shares > 0 ? (
                    <span className={cn("font-medium", pnl >= 0 ? "text-green-500" : "text-red-500")}>
                      {fmtPnL(pnl)}<span className="text-[10px] ml-0.5">({fmtPct(pnlPct)})</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className={cn("px-2.5 py-2 text-[10px] font-medium", getFundColor(s))}>
                  {getFundQuick(s)}
                </td>
                <td className={cn("px-2.5 py-2 text-[10px] font-medium", getAlphaColor(s))}>
                  {getAlphaQuick(s)}
                </td>
                <td className="px-2.5 py-2">
                  {techDim ? (
                    <div className="flex flex-col gap-0.5">
                      <span className={cn("inline-flex items-center gap-1 text-[10px]", s.trend.direction === "up" ? "text-green-500" : s.trend.direction === "down" ? "text-red-500" : "text-muted-foreground")}>
                        <DirIcon className="w-3 h-3" />
                        {s.trend.ma_pattern}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{techDim.summary}</span>
                    </div>
                  ) : (
                    <span className={cn("inline-flex items-center gap-1 text-xs", s.trend.direction === "up" ? "text-green-500" : s.trend.direction === "down" ? "text-red-500" : "text-muted-foreground")}>
                      <DirIcon className="w-3 h-3" />
                      {s.trend.ma_pattern}
                    </span>
                  )}
                </td>
                <td className="px-2.5 py-2 text-center">
                  <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border", DECISION_COLORS[s.decision] || DECISION_COLORS.hold)}>
                    <Circle className="w-1.5 h-1.5 fill-current" />
                    {s.decision_label}
                  </span>
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

export function PositionDecision() {
  const { dark } = useDarkMode();
  const [positions, setPositions] = useState<Position[]>([]);
  const [watchlistReady, setWatchlistReady] = useState(false);
  const [signals, setSignals] = useState<PositionSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PositionSignal | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // AI analysis state — per-symbol cache, survives stock switches and page refresh
  const AI_CACHE_KEY = "vibe-position-ai-cache";
  const [aiCache, setAiCache] = useState<Record<string, string>>(() => {
    try {
      const raw = localStorage.getItem(AI_CACHE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  });
  const [aiLoading, setAiLoading] = useState(false);
  const [aiStreaming, setAiStreaming] = useState("");

  // Derive current AI content from cache based on selected symbol
  const aiContent: string | null = selected ? aiCache[selected.symbol] ?? null : null;

  // Add form state
  const [showAdd, setShowAdd] = useState(false);
  const [addSymbol, setAddSymbol] = useState("");
  const [addCost, setAddCost] = useState("");
  const [addShares, setAddShares] = useState("");
  const [addDate, setAddDate] = useState(() => new Date().toISOString().slice(0, 10));

  const positionsRef = useRef(positions);
  positionsRef.current = positions;
  const signalsRef = useRef(signals);
  signalsRef.current = signals;

  // --- Load watchlist from server on mount, fall back to localStorage ---
  useEffect(() => {
    let cancelled = false;
    api.getWatchlist()
      .then((res) => {
        if (cancelled) return;
        if (res.items && res.items.length > 0) {
          setPositions(res.items);
          // Sync server data to localStorage
          localStorage.setItem(LS_KEY, JSON.stringify(res.items));
        } else {
          // Server empty — try localStorage
          setPositions(loadPositions());
        }
      })
      .catch(() => {
        // Server unreachable — fall back to localStorage
        if (!cancelled) setPositions(loadPositions());
      })
      .finally(() => {
        if (!cancelled) setWatchlistReady(true);
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const analyze = useCallback((silent = false) => {
    if (!silent) setRefreshing(true);
    const list = positionsRef.current;
    if (!list.length) {
      setSignals([]);
      setLoading(false);
      setRefreshing(false);
      return;
    }

    const symbols = list.map((p) => p.symbol);
    // Append cache-bust on manual refresh so user sees fresh data
    const body: { symbols: string[]; _cache_bust?: number } = { symbols };
    if (!silent) body._cache_bust = Date.now();

    api.analyzePositions(body)
      .then((res) => {
        setSignals(res.signals);
        setError(null);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "分析失败";
        if (!signalsRef.current.length) setError(msg);
        else toast.error(msg);
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initial load — wait for watchlist to be loaded from server/localStorage
  useEffect(() => {
    if (!watchlistReady) return;
    if (positions.length) {
      setLoading(true);
      analyze(true);
    } else {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchlistReady]);

  // Auto-refresh
  useEffect(() => {
    intervalRef.current = setInterval(() => { if (positions.length) analyze(true); }, REFRESH_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Normalize plain 6-digit code to exchange-suffixed form
  const normalizeCode = (input: string): string => {
    const cleaned = input.trim().toUpperCase();
    // Already suffixed
    if (/^\d{6}\.(SZ|SH)$/.test(cleaned)) return cleaned;
    // Plain 6-digit
    if (/^\d{6}$/.test(cleaned)) {
      const prefix = cleaned.substring(0, 3);
      // Shenzhen: 000-004, 300-301, 159 (SZ ETFs)
      if (["000", "001", "002", "003", "004", "159", "300", "301"].includes(prefix)) return cleaned + ".SZ";
      // Shanghai: 5xx ETFs, 6xx stocks, 688 STAR
      if (["600", "601", "603", "605", "688", "689"].includes(prefix)) return cleaned + ".SH";
      if (prefix.startsWith("5")) return cleaned + ".SH";  // ETFs: 51x, 56x, 58x etc
      return cleaned + ".SH"; // default guess (more likely SH for unknown)
    }
    return "";
  };

  // Add position
  const addPosition = () => {
    const code = normalizeCode(addSymbol);
    if (!code) {
      toast.error("请输入6位股票代码，如 000001");
      return;
    }
    if (positions.find((p) => p.symbol === code)) {
      toast.error("已在自选列表中");
      return;
    }
    const cost = parseFloat(addCost) || 0;
    const shares = parseInt(addShares) || 0;
    const next = [...positions, { symbol: code, cost, shares, date: addDate }];
    setPositions(next);
    savePositions(next);
    setAddSymbol("");
    setAddCost("");
    setAddShares("");
    setAddDate(new Date().toISOString().slice(0, 10));
    setShowAdd(false);
    // Trigger immediate analysis
    const syms = next.map((p) => p.symbol);
    api.analyzePositions({ symbols: syms })
      .then((res) => { setSignals(res.signals); setError(null); })
      .catch((err) => { setError(err instanceof Error ? err.message : "分析失败"); })
      .finally(() => setLoading(false));
  };

  // Remove position
  const removePosition = (code: string) => {
    const next = positions.filter((p) => p.symbol !== code);
    setPositions(next);
    savePositions(next);
    api.removeWatchlistItem(code).catch(() => {});
    if (selected?.symbol === code) setSelected(null);
    if (next.length) {
      const syms = next.map((p) => p.symbol);
      api.analyzePositions({ symbols: syms })
        .then((res) => setSignals(res.signals))
        .catch(() => {});
    } else {
      setSignals([]);
    }
  };

  // AI cache is per-symbol — no need to clear on switch.
  // When user comes back to a previously analyzed stock, cached result is shown.

  // Run AI deep analysis via SSE
  const runAiAnalysis = async () => {
    if (!selected) return;
    const symbol = selected.symbol;
    setAiLoading(true);
    setAiStreaming("");

    const pos = positions.find((p) => p.symbol === symbol);
    try {
      console.log("[AI] Starting analysis for", selected.symbol);
      const response = await api.aiAnalyzePosition(
        selected.symbol, selected, pos ? { cost: pos.cost, shares: pos.shares } : undefined,
      );
      console.log("[AI] Response status:", response.status);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let finalText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) { console.log("[AI] Stream done"); break; }
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events — only process complete event blocks
        const parts = buffer.split("\n\n");
        // Keep incomplete last part in buffer
        buffer = parts.pop() || "";

        for (const block of parts) {
          const lines = block.split("\n");
          let eventType = "";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6);
          }
          if (!eventType || !dataStr) continue;
          try {
            const data = JSON.parse(dataStr);
            if (eventType === "text_delta") {
              setAiStreaming((prev) => prev + (data.delta || ""));
            } else if (eventType === "analysis_complete") {
              finalText = data.content || "";
              setAiCache((prev) => {
                const next = { ...prev, [symbol]: finalText };
                localStorage.setItem(AI_CACHE_KEY, JSON.stringify(next));
                return next;
              });
              setAiStreaming("");
              console.log("[AI] Complete:", finalText.slice(0, 100));
            }
          } catch { /* skip parse errors */ }
        }
      }
      if (!finalText) {
        const fallback = "AI 分析完成，但未返回内容";
        setAiCache((prev) => {
          const next = { ...prev, [symbol]: fallback };
          localStorage.setItem(AI_CACHE_KEY, JSON.stringify(next));
          return next;
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误";
      console.error("[AI] Error:", msg, err);
      const errMsg = `AI 分析失败: ${msg}`;
      setAiCache((prev) => {
        const next = { ...prev, [symbol]: errMsg };
        localStorage.setItem(AI_CACHE_KEY, JSON.stringify(next));
        return next;
      });
      toast.error("AI 分析失败");
    } finally {
      setAiLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") addPosition();
  };

  const selectedPos = positions.find((p) => p.symbol === selected?.symbol);
  const posMap = new Map(positions.map((p) => [p.symbol, p]));

  // Calculate portfolio totals
  const totalPnL = signals.reduce((sum, s) => {
    const pos = posMap.get(s.symbol);
    return pos && pos.shares > 0 ? sum + (s.price - pos.cost) * pos.shares : sum;
  }, 0);
  const totalValue = signals.reduce((sum, s) => {
    const pos = posMap.get(s.symbol);
    return pos && pos.shares > 0 ? sum + s.price * pos.shares : sum;
  }, 0);

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b shrink-0">
        <div>
          <h1 className="text-lg font-semibold">持仓决策</h1>
          <p className="text-xs text-muted-foreground">A股多因子信号分析 · 数据源 通达信(mootdx)</p>
        </div>
        <div className="flex items-center gap-2">
          {positions.length > 0 && (
            <span className="text-[10px] text-muted-foreground hidden sm:inline">
              总市值 {fmtMoney(totalValue)} · 盈亏 {fmtPnL(totalPnL)}
            </span>
          )}
          <button
            onClick={() => analyze()}
            disabled={refreshing || !positions.length}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            aria-label="刷新"
          >
            <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left: watchlist */}
        <aside className="w-[210px] shrink-0 border-r overflow-y-auto p-3 space-y-3 hidden md:block">
          {/* Portfolio summary */}
          {positions.length > 0 && (
            <div className="bg-muted/40 rounded-lg p-3 space-y-1.5">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Wallet className="w-3.5 h-3.5" />
                <span className="text-[10px] font-medium">持仓总览</span>
              </div>
              <p className="text-lg font-bold tabular-nums">{fmtMoney(totalValue)}</p>
              <p className={cn("text-xs font-medium flex items-center gap-1", totalPnL >= 0 ? "text-green-500" : "text-red-500")}>
                {totalPnL >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {fmtPnL(totalPnL)}
              </p>
            </div>
          )}

          {/* Add form */}
          {showAdd ? (
            <div className="space-y-2 p-2 border rounded-lg bg-muted/20">
              <input
                type="text"
                value={addSymbol}
                onChange={(e) => setAddSymbol(e.target.value)}
                onKeyDown={handleKey}
                placeholder="代码 000001.SZ"
                className="w-full px-2 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
              <div className="space-y-1.5">
                <input
                  type="number"
                  value={addCost}
                  onChange={(e) => setAddCost(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="成本价（选填）"
                  step="0.01"
                  className="w-full px-2 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <input
                  type="number"
                  value={addShares}
                  onChange={(e) => setAddShares(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="股数（选填）"
                  step="100"
                  className="w-full px-2 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <input
                  type="date"
                  value={addDate}
                  onChange={(e) => setAddDate(e.target.value)}
                  className="w-full px-2 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex gap-1">
                <button onClick={addPosition} className="flex-1 px-2 py-1.5 text-xs rounded-md bg-primary text-primary-foreground font-medium">
                  确认添加
                </button>
                <button onClick={() => { setShowAdd(false); setAddSymbol(""); setAddCost(""); setAddShares(""); setAddDate(new Date().toISOString().slice(0, 10)); }} className="px-2 py-1.5 text-xs rounded-md border text-muted-foreground hover:text-foreground">
                  取消
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowAdd(true)}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg border border-dashed border-muted-foreground/30 text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              添加自选股
            </button>
          )}

          {/* Watchlist */}
          <div className="space-y-0.5">
            <p className="text-[10px] text-muted-foreground font-medium px-1">自选股 ({positions.length})</p>
            {positions.length === 0 && (
              <p className="text-[10px] text-muted-foreground px-1 py-4 text-center">
                暂无自选，点击上方按钮添加
              </p>
            )}
            {positions.map((pos) => {
              const sig = signals.find((s) => s.symbol === pos.symbol);
              const pnl = sig && pos.shares > 0 ? (sig.price - pos.cost) * pos.shares : 0;

              return (
                <div
                  key={pos.symbol}
                  className={cn(
                    "flex items-center gap-2 px-2 py-1.5 rounded-md text-xs group cursor-pointer transition-colors hover:bg-muted",
                    selected?.symbol === pos.symbol && "bg-primary/10",
                  )}
                  onClick={() => sig && setSelected(sig)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1">
                      <p className="font-medium truncate text-xs">{sig?.name || pos.symbol}</p>
                      {pos.shares > 0 && (
                        <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">{pos.shares}股</span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground font-mono">{pos.symbol}</p>
                    {sig ? (
                      <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                        <span className="tabular-nums">¥{fmtPrice(sig.price)}</span>
                        <span className={cn("tabular-nums font-medium", sig.change_pct >= 0 ? "text-green-500" : "text-red-500")}>
                          {fmtPct(sig.change_pct)}
                        </span>
                        {pos.shares > 0 && (
                          <span className={cn("tabular-nums font-medium ml-auto", pnl >= 0 ? "text-green-500" : "text-red-500")}>
                            {fmtPnL(pnl)}
                          </span>
                        )}
                      </div>
                    ) : (
                      pos.cost > 0 && <p className="text-[10px] text-muted-foreground mt-0.5">成本 ¥{fmtPrice(pos.cost)}{pos.date ? ` · ${pos.date.slice(5)}` : ""}</p>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); removePosition(pos.symbol); }}
                    className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-all shrink-0"
                    aria-label="删除"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Mobile add bar */}
        <div className="md:hidden px-4 py-2 border-b flex flex-col gap-2">
          {showAdd ? (
            <div className="flex gap-1">
              <input type="text" value={addSymbol} onChange={(e) => setAddSymbol(e.target.value)} onKeyDown={handleKey} placeholder="代码" className="w-24 px-2 py-1.5 text-xs rounded-md border bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary" />
              <input type="number" value={addCost} onChange={(e) => setAddCost(e.target.value)} onKeyDown={handleKey} placeholder="成本" className="w-16 px-2 py-1.5 text-xs rounded-md border bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary" />
              <input type="number" value={addShares} onChange={(e) => setAddShares(e.target.value)} onKeyDown={handleKey} placeholder="股数" className="w-14 px-2 py-1.5 text-xs rounded-md border bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary" />
              <button onClick={addPosition} className="px-2 py-1.5 text-xs rounded-md bg-primary text-primary-foreground">添加</button>
              <button onClick={() => { setShowAdd(false); setAddSymbol(""); setAddCost(""); setAddShares(""); }} className="px-2 py-1.5 text-xs rounded-md border">取消</button>
            </div>
          ) : (
            <button onClick={() => setShowAdd(true)} className="w-full text-xs py-1.5 rounded-md border border-dashed text-muted-foreground">
              <Plus className="w-3 h-3 inline mr-1" />添加自选股
            </button>
          )}
        </div>

        {/* Main: table + detail */}
        <div className="flex-1 flex overflow-hidden">
          <div className={cn("flex-1 overflow-y-auto", selected ? "hidden lg:block" : "")}>
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                <AlertTriangle className="w-8 h-8" />
                <p className="text-sm">{error}</p>
                <button onClick={() => analyze()} className="text-xs text-primary hover:underline">重试</button>
              </div>
            ) : !positions.length ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                <Target className="w-10 h-10 opacity-30" />
                <p className="text-sm">暂无自选股</p>
                <p className="text-xs">点击左侧「添加自选股」开始分析</p>
              </div>
            ) : (
              <>
                <div className="px-4 py-2 border-b flex items-center gap-2">
                  <span className="text-[10px] text-muted-foreground">数据源</span>
                  <span className="text-xs font-medium px-2 py-0.5 rounded bg-muted">通达信 (mootdx)</span>
                  <span className="text-[10px] text-muted-foreground ml-auto">{signals.length} 个标的</span>
                </div>
                <SignalTable signals={signals} positions={positions} selected={selected?.symbol ?? null} onSelect={setSelected} dark={dark} />
              </>
            )}
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="hidden lg:block w-[380px] shrink-0 border-l overflow-y-auto p-4">
              <DetailPanel signal={selected} position={selectedPos} onClose={() => setSelected(null)} dark={dark} aiLoading={aiLoading} aiContent={aiContent} aiStreaming={aiStreaming} onAiAnalyze={runAiAnalysis} />
            </div>
          )}

          {/* Mobile detail */}
          {selected && (
            <div className="lg:hidden fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
              <div className="absolute inset-x-0 bottom-0 top-12 overflow-y-auto p-4">
                <DetailPanel signal={selected} position={selectedPos} onClose={() => setSelected(null)} dark={dark} aiLoading={aiLoading} aiContent={aiContent} aiStreaming={aiStreaming} onAiAnalyze={runAiAnalysis} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
