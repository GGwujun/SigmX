import { useState, useEffect } from "react";
import { Search, Loader2, AlertTriangle, TrendingUp, TrendingDown, Target, GitBranch, Globe, Building2, FileText, Banknote, Newspaper, Shield, ChevronDown } from "lucide-react";
import { api, type LogicChainResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const ICONS: Record<string, typeof Globe> = {
  globe: Globe, building: Building2, "file-text": FileText, "trending-up": TrendingUp,
  banknote: Banknote, newspaper: Newspaper, shield: Shield,
};

function fmtPrice(p: number): string { return p >= 1000 ? p.toFixed(0) : p.toFixed(2); }
function fmtPct(p: number): string { return `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`; }

export function LogicChain() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<LogicChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["technical"]));

  const analyze = async (c?: string) => {
    const target = (c || code).trim().toUpperCase();
    if (!target) return;
    // Normalize plain code
    let normalized = target;
    if (/^\d{6}$/.test(target)) {
      const pfx = target.substring(0, 3);
      normalized = ["000","001","002","003","004","159","300","301"].includes(pfx) ? target + ".SZ" : target + ".SH";
    }
    if (!/^\d{6}\.(SZ|SH)$/.test(normalized)) {
      toast.error("请输入有效代码"); return;
    }

    setLoading(true); setError(null);
    try {
      const res = await api.getLogicChain(normalized);
      setResult(res);
      setExpanded(new Set(["technical"]));
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析失败");
    } finally { setLoading(false); }
  };

  const toggleLayer = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b shrink-0">
        <div>
          <h1 className="text-lg font-semibold">逻辑链</h1>
          <p className="text-xs text-muted-foreground">八层递进推理 · 从宏观到决策</p>
        </div>
      </div>

      {/* Input bar */}
      <div className="px-4 md:px-6 py-3 border-b shrink-0 flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text" value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && analyze()}
            placeholder="输入代码，如 000001"
            className="w-full pl-8 pr-3 py-2 text-sm rounded-lg border bg-muted/40 focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <button onClick={() => analyze()} disabled={loading || !code.trim()}
          className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-40">
          分析
        </button>
        {/* Quick picks */}
        {["000001", "600519", "300750"].map((qc) => (
          <button key={qc} onClick={() => { setCode(qc); analyze(qc); }}
            className="px-2 py-2 text-xs rounded-lg border text-muted-foreground hover:text-foreground hover:bg-muted hidden sm:block">
            {qc}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <AlertTriangle className="w-8 h-8" /><p className="text-sm">{error}</p>
            <button onClick={() => analyze()} className="text-xs text-primary hover:underline">重试</button>
          </div>
        ) : !result ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <GitBranch className="w-12 h-12 opacity-20" />
            <p className="text-sm">输入股票代码开始八层逻辑分析</p>
            <p className="text-xs">系统将自动从宏观环境逐层推导至交易决策</p>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-4">
            {/* Stock header */}
            <div className="flex items-center justify-between p-4 rounded-xl border bg-card">
              <div>
                <h2 className="text-xl font-bold">{result.name} <span className="text-sm font-normal text-muted-foreground">{result.code}</span></h2>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold tabular-nums">¥{fmtPrice(result.price)}</p>
                <p className={cn("text-sm font-medium", result.change_pct >= 0 ? "text-green-500" : "text-red-500")}>
                  {result.change_pct >= 0 ? <TrendingUp className="w-3.5 h-3.5 inline mr-0.5" /> : <TrendingDown className="w-3.5 h-3.5 inline mr-0.5" />}
                  {fmtPct(result.change_pct)}
                </p>
              </div>
            </div>

            {/* Layers */}
            {result.layers.map((layer, i) => {
              const Icon = ICONS[layer.icon] || Globe;
              const isExpanded = expanded.has(layer.id);
              return (
                <div key={layer.id} className="relative">
                  {/* Connector line */}
                  {i < result.layers.length - 1 && (
                    <div className="absolute left-5 top-full h-4 w-px bg-border" />
                  )}

                  <div className="rounded-xl border bg-card overflow-hidden">
                    <button onClick={() => toggleLayer(layer.id)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors">
                      <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                        layer.score >= 0.6 ? "bg-green-500/10" : layer.score >= 0.4 ? "bg-amber-500/10" : "bg-red-500/10")}>
                        <Icon className={cn("w-4 h-4",
                          layer.score >= 0.6 ? "text-green-500" : layer.score >= 0.4 ? "text-amber-500" : "text-red-500")} />
                      </div>
                      <div className="flex-1">
                        <span className="text-sm font-medium">{layer.label}</span>
                        <span className="ml-2 text-lg">{layer.signal}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">{(layer.score * 100).toFixed(0)}分</span>
                        <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="px-4 pb-3 border-t">
                        <div className="grid grid-cols-2 gap-2 mt-3">
                          {layer.items.map((item) => (
                            <div key={item.label} className="flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2">
                              <span className="text-xs text-muted-foreground">{item.label}</span>
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-medium">{item.value}</span>
                                <span>{item.signal}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                        {/* Progress bar */}
                        <div className="mt-3 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                          <div className={cn("h-full rounded-full transition-all",
                            layer.score >= 0.6 ? "bg-green-500" : layer.score >= 0.4 ? "bg-amber-500" : "bg-red-500")}
                            style={{ width: `${layer.score * 100}%` }} />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Decision card */}
            <div className={cn("rounded-xl border-2 p-6",
              result.decision.score >= 0.6 ? "border-green-500/40 bg-green-500/5" :
              result.decision.score >= 0.4 ? "border-amber-500/40 bg-amber-500/5" :
              "border-red-500/40 bg-red-500/5")}>
              <div className="flex items-center gap-3 mb-4">
                <Target className="w-6 h-6 text-primary" />
                <h3 className="text-lg font-bold">综合决策</h3>
                <span className="text-2xl ml-auto">{result.decision.signal}</span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-background rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold">{result.decision.signal} {result.decision.action}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">操作建议</p>
                </div>
                <div className="bg-background rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold tabular-nums">{result.decision.position_pct}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">建议仓位</p>
                </div>
                <div className="bg-background rounded-lg p-3 text-center">
                  <p className="text-lg font-bold tabular-nums text-red-500">¥{fmtPrice(result.decision.stop_loss)}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">止损位</p>
                </div>
                <div className="bg-background rounded-lg p-3 text-center">
                  <p className="text-lg font-bold tabular-nums text-green-500">¥{fmtPrice(result.decision.take_profit)}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">止盈位</p>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-4 text-xs text-muted-foreground">
                <span>综合评分 <strong className="text-foreground">{result.decision.score.toFixed(2)}</strong></span>
                <span>盈亏比 <strong className="text-foreground">1:{result.decision.risk_reward}</strong></span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
