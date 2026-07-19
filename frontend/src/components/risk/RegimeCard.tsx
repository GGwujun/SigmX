import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface RegimeData {
  trade_date: string;
  regime: string;
  confidence: number;
  bull_score: number;
  bear_score: number;
  strong_trend: boolean;
  technical_indicators: Record<string, unknown>;
  parameters: Record<string, unknown>;
}

const REGIME_CONFIG: Record<string, { label: string; color: string; bg: string; icon: typeof TrendingUp }> = {
  bull: { label: "牛市", color: "text-green-400", bg: "bg-green-500/10 border-green-500/30", icon: TrendingUp },
  bear: { label: "熊市", color: "text-red-400", bg: "bg-red-500/10 border-red-500/30", icon: TrendingDown },
  range: { label: "震荡", color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/30", icon: Minus },
};

export function RegimeCard({ data }: { data: RegimeData | null }) {
  if (!data) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-center text-sm text-white/40">
        暂无市场环境数据
      </div>
    );
  }

  const config = REGIME_CONFIG[data.regime] || REGIME_CONFIG.range;
  const Icon = config.icon;
  const indicators = data.technical_indicators || {};
  const params = data.parameters || {};

  return (
    <div className={cn("rounded-xl border p-6", config.bg)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Icon className={cn("h-6 w-6", config.color)} />
          <div>
            <div className={cn("text-2xl font-bold", config.color)}>{config.label}</div>
            <div className="text-xs text-white/50">{data.trade_date}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm text-white/60">置信度</div>
          <div className={cn("text-3xl font-bold", config.color)}>{data.confidence.toFixed(0)}%</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-lg bg-white/5 p-3">
          <div className="text-xs text-white/40">多头得分</div>
          <div className="text-lg font-semibold text-green-400">{data.bull_score.toFixed(1)}</div>
        </div>
        <div className="rounded-lg bg-white/5 p-3">
          <div className="text-xs text-white/40">空头得分</div>
          <div className="text-lg font-semibold text-red-400">{data.bear_score.toFixed(1)}</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">RSI </span>
          <span className="font-mono text-white/80">{((indicators.rsi14 as number) || 0).toFixed(1)}</span>
        </div>
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">ADX </span>
          <span className="font-mono text-white/80">{((indicators.adx as number) || 0).toFixed(1)}</span>
        </div>
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">波动率 </span>
          <span className="font-mono text-white/80">{((indicators.volatility as number) || 0).toFixed(1)}%</span>
        </div>
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">止损 </span>
          <span className="font-mono text-white/80">{((params.stop_loss as number) || 0) * 100}%</span>
        </div>
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">仓位上限 </span>
          <span className="font-mono text-white/80">{((params.max_position as number) || 0) * 100}%</span>
        </div>
        <div className="rounded bg-white/5 px-2 py-1.5">
          <span className="text-white/40">最多持仓 </span>
          <span className="font-mono text-white/80">{(params.max_holdings as number) || 0} 只</span>
        </div>
      </div>
    </div>
  );
}
