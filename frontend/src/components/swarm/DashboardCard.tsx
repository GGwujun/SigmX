import { cn } from "@/lib/utils";

interface DashboardData {
  core_conclusion: {
    one_sentence: string;
    signal_type: string;
    bull_bear_summary: string;
  };
  technical: {
    trend: string;
    support: number;
    resistance: number;
    ma_alignment: string;
    trend_score: number;
  };
  fundamental: {
    valuation: string;
    growth: string;
    quality_score: number;
  };
  capital_flow: {
    main_net: number;
    northbound: string;
    sentiment: string;
  };
  battle_plan: {
    entry_price: number;
    stop_loss: number;
    target_1: number;
    target_2: number;
    risk_reward: number;
  };
  risk_factors: string[];
  catalysts: string[];
}

const SIGNAL_COLORS: Record<string, string> = {
  "🟢买入信号": "text-green-400 bg-green-500/10 border-green-500/30",
  "🟡持有观望": "text-yellow-400 bg-yellow-500/10 border-yellow-500/30",
  "🔴卖出信号": "text-red-400 bg-red-500/10 border-red-500/30",
  "⚠️风险警告": "text-orange-400 bg-orange-500/10 border-orange-500/30",
};

function ScoreBar({ value, label }: { value: number; label: string }) {
  const color = value >= 70 ? "bg-green-500" : value >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-white/50">{label}</span>
        <span className="text-white/70 font-mono">{value}</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function PriceTag({ label, value }: { label: string; value: number }) {
  if (!value) return null;
  return (
    <div className="text-center">
      <div className="text-xs text-white/40">{label}</div>
      <div className="text-sm font-mono font-semibold text-white/80">{value.toFixed(2)}</div>
    </div>
  );
}

export function DashboardCard({ dashboard, decision, confidence }: {
  dashboard: DashboardData;
  decision: string;
  confidence: number;
}) {
  const signalClass = SIGNAL_COLORS[dashboard.core_conclusion?.signal_type] || SIGNAL_COLORS["🟡持有观望"];
  const bp = dashboard.battle_plan;
  const riskReward = bp?.risk_reward || 0;

  return (
    <div className="space-y-4">
      {/* 核心结论 */}
      <div className={cn("rounded-xl border p-4", signalClass)}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-lg font-bold">{dashboard.core_conclusion?.signal_type}</span>
          <span className="text-sm opacity-70">置信度 {(confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="text-sm font-medium mb-1">{dashboard.core_conclusion?.one_sentence}</div>
        {dashboard.core_conclusion?.bull_bear_summary && (
          <div className="text-xs opacity-70 mt-2">{dashboard.core_conclusion.bull_bear_summary}</div>
        )}
      </div>

      {/* 作战计划 */}
      {bp && (bp.entry_price || bp.stop_loss || bp.target_1) && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <h4 className="text-sm font-semibold text-white/70 mb-3">⚔️ 作战计划</h4>
          <div className="grid grid-cols-4 gap-2">
            <PriceTag label="入场" value={bp.entry_price} />
            <PriceTag label="止损" value={bp.stop_loss} />
            <PriceTag label="目标1" value={bp.target_1} />
            <PriceTag label="目标2" value={bp.target_2} />
          </div>
          {riskReward > 0 && (
            <div className="mt-3 text-center text-xs text-white/50">
              盈亏比 <span className="font-mono text-white/80 font-semibold">{riskReward.toFixed(1)}</span>
            </div>
          )}
        </div>
      )}

      {/* 技术面 + 基本面 + 资金面 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 技术面 */}
        {dashboard.technical && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <h4 className="text-sm font-semibold text-white/70 mb-2">📊 技术面</h4>
            {dashboard.technical.trend_score > 0 && (
              <ScoreBar value={dashboard.technical.trend_score} label="趋势得分" />
            )}
            {dashboard.technical.trend && (
              <div className="text-xs text-white/60 mt-2">{dashboard.technical.trend}</div>
            )}
            {dashboard.technical.ma_alignment && (
              <div className="text-xs text-white/50 mt-1">均线: {dashboard.technical.ma_alignment}</div>
            )}
          </div>
        )}

        {/* 基本面 */}
        {dashboard.fundamental && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <h4 className="text-sm font-semibold text-white/70 mb-2">📈 基本面</h4>
            {dashboard.fundamental.quality_score > 0 && (
              <ScoreBar value={dashboard.fundamental.quality_score} label="质量得分" />
            )}
            {dashboard.fundamental.valuation && (
              <div className="text-xs text-white/60 mt-2">估值: {dashboard.fundamental.valuation}</div>
            )}
            {dashboard.fundamental.growth && (
              <div className="text-xs text-white/50 mt-1">成长: {dashboard.fundamental.growth}</div>
            )}
          </div>
        )}

        {/* 资金面 */}
        {dashboard.capital_flow && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <h4 className="text-sm font-semibold text-white/70 mb-2">💰 资金面</h4>
            {dashboard.capital_flow.main_net !== 0 && (
              <div className="text-xs mt-1">
                主力净流入: <span className={cn("font-mono font-semibold",
                  dashboard.capital_flow.main_net > 0 ? "text-red-400" : "text-green-400"
                )}>
                  {(dashboard.capital_flow.main_net / 10000).toFixed(1)}亿
                </span>
              </div>
            )}
            {dashboard.capital_flow.northbound && (
              <div className="text-xs text-white/60 mt-1">北向: {dashboard.capital_flow.northbound}</div>
            )}
            {dashboard.capital_flow.sentiment && (
              <div className="text-xs text-white/50 mt-1">情绪: {dashboard.capital_flow.sentiment}</div>
            )}
          </div>
        )}
      </div>

      {/* 风险 + 催化 */}
      {(dashboard.risk_factors?.length > 0 || dashboard.catalysts?.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {dashboard.risk_factors?.length > 0 && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
              <h4 className="text-sm font-semibold text-red-400 mb-2">⚠️ 风险因素</h4>
              <ul className="space-y-1">
                {dashboard.risk_factors.map((r, i) => (
                  <li key={i} className="text-xs text-white/60">• {r}</li>
                ))}
              </ul>
            </div>
          )}
          {dashboard.catalysts?.length > 0 && (
            <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4">
              <h4 className="text-sm font-semibold text-green-400 mb-2">🚀 催化因素</h4>
              <ul className="space-y-1">
                {dashboard.catalysts.map((c, i) => (
                  <li key={i} className="text-xs text-white/60">• {c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
