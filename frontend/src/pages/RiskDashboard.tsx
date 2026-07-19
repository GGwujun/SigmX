import { useCallback, useEffect, useState } from "react";
import { Shield, RefreshCw, AlertTriangle, Activity } from "lucide-react";
import { RegimeCard } from "@/components/risk/RegimeCard";
import { RiskMatrix } from "@/components/risk/RiskMatrix";
import { HealthScore } from "@/components/risk/HealthScore";

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

interface RiskCheck {
  layer: number;
  name: string;
  triggered: boolean;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  action: string;
}

interface RiskCheckData {
  trade_date: string;
  regime: string;
  checks: RiskCheck[];
  portfolio_health_score: number;
  summary: string;
}

interface RiskEvent {
  event_id: string;
  trade_date: string;
  layer: number;
  severity: string;
  code: string | null;
  message: string;
  created_at: string;
}

async function fetchJSON<T>(url: string): Promise<T> {
  const token = localStorage.getItem("auth_token");
  const resp = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export default function RiskDashboard() {
  const [regime, setRegime] = useState<RegimeData | null>(null);
  const [riskCheck, setRiskCheck] = useState<RiskCheckData | null>(null);
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [regimeData, checkData, eventsData] = await Promise.all([
        fetchJSON<RegimeData>("/api/v1/risk/regime"),
        fetchJSON<RiskCheckData>("/api/v1/risk/check"),
        fetchJSON<{ events: RiskEvent[] }>("/api/v1/risk/check/history?days=7&limit=20"),
      ]);
      setRegime(regimeData);
      setRiskCheck(checkData);
      setEvents(eventsData.events || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const runCheck = async () => {
    setLoading(true);
    try {
      const data = await fetchJSON<RiskCheckData>("/api/v1/risk/check");
      setRiskCheck(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检查失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-blue-400" />
          <h1 className="text-xl font-bold text-white">风控看板</h1>
        </div>
        <button
          onClick={runCheck}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-blue-500/20 border border-blue-500/30 px-4 py-2 text-sm text-blue-400 hover:bg-blue-500/30 disabled:opacity-50 transition"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          运行风控检查
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Top row: Regime + Health Score */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <RegimeCard data={regime} />
        </div>
        <HealthScore score={riskCheck?.portfolio_health_score ?? 100} />
      </div>

      {/* Risk Matrix */}
      <RiskMatrix checks={riskCheck?.checks || []} />

      {/* Summary */}
      {riskCheck?.summary && (
        <div className="rounded-lg bg-white/5 border border-white/10 p-4 text-center">
          <span className="text-sm text-white/60">{riskCheck.summary}</span>
        </div>
      )}

      {/* Events timeline */}
      {events.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10 flex items-center gap-2">
            <Activity className="h-4 w-4 text-white/50" />
            <h3 className="text-sm font-semibold text-white/80">风控事件（近 7 天）</h3>
          </div>
          <div className="divide-y divide-white/5 max-h-80 overflow-y-auto">
            {events.map((e) => (
              <div key={e.event_id} className="px-4 py-2.5 flex items-start gap-3">
                <AlertTriangle className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
                  e.severity === "critical" ? "text-red-400" :
                  e.severity === "warning" ? "text-yellow-400" : "text-blue-400"
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white/70">{e.message}</div>
                  <div className="text-xs text-white/40 mt-0.5">
                    L{e.layer} · {e.created_at?.replace("T", " ").slice(0, 16)}
                    {e.code && ` · ${e.code}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
