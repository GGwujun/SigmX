import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";
import { api, type FundScanItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const FUND_TYPES = [
  { value: "ETF", label: "ETF" },
  { value: "LOF", label: "LOF" },
  { value: "ALL", label: "全部" },
];

function premiumClass(p: number): string {
  if (p > 1.5) return "text-danger font-semibold";
  if (p > 0.5) return "text-warning";
  if (p < -1.5) return "text-success font-semibold";
  if (p < -0.5) return "text-success";
  return "text-muted-foreground";
}

function fmtAmt(n: number): string {
  if (n >= 1e8) return (n / 1e8).toFixed(2) + "亿";
  if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
  return n.toFixed(0);
}

export function FundOpportunity() {
  const navigate = useNavigate();
  const [fundType, setFundType] = useState("ETF");
  const [minPremium, setMinPremium] = useState(0.5);
  const [items, setItems] = useState<FundScanItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState("");

  const doScan = useCallback(async (showToast = false) => {
    setLoading(true);
    try {
      const res = await api.scanFunds(fundType, minPremium, 80);
      setItems(res.items || []);
      setUpdatedAt(new Date().toLocaleTimeString());
      if (showToast) toast.success(`扫描到 ${res.count} 只基金`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "扫描失败");
    } finally {
      setLoading(false);
    }
  }, [fundType, minPremium]);

  useEffect(() => {
    doScan(); // auto-scan on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const goAnalyze = (item: FundScanItem) => {
    navigate(`/fund-arbitrage?code=${encodeURIComponent(item.code)}&type=${encodeURIComponent(item.type)}`);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* header */}
      <header className="border-b px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Search className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold">套利机会</h1>
            <p className="text-xs text-muted-foreground">
              LOF/ETF 折溢价扫描{updatedAt ? ` · 更新于 ${updatedAt}` : ""}
            </p>
          </div>
        </div>
        <button onClick={() => doScan(true)} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-40">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          刷新
        </button>
      </header>

      {/* filters */}
      <div className="border-b px-6 py-3 flex flex-wrap items-center gap-3 shrink-0 bg-muted/20">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">类型</span>
          <select value={fundType} onChange={e => setFundType(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg border bg-background text-sm">
            {FUND_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">最小折溢价</span>
          <input type="number" step="0.1" value={minPremium} onChange={e => setMinPremium(parseFloat(e.target.value) || 0)}
            className="w-20 px-2 py-1.5 rounded-lg border bg-background text-sm" />
          <span className="text-xs text-muted-foreground">%</span>
        </div>
        <button onClick={() => doScan(true)} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-medium hover:bg-background disabled:opacity-40">
          <Search className="h-3.5 w-3.5" /> 扫描
        </button>
      </div>

      {/* table */}
      <div className="flex-1 overflow-auto p-6">
        {loading && items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm">扫描中…（首次约 20 秒）</p>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
            <Coins className="h-12 w-12 opacity-30" />
            <p className="text-sm">未发现符合条件的套利机会</p>
            <p className="text-xs opacity-60">尝试降低最小折溢价阈值，或切换基金类型</p>
          </div>
        ) : (
          <div className="rounded-lg border overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-xs text-muted-foreground sticky top-0">
                <tr>
                  <th className="text-left px-3 py-2.5 font-medium">代码</th>
                  <th className="text-left px-3 py-2.5 font-medium">名称</th>
                  <th className="text-right px-3 py-2.5 font-medium">场内价</th>
                  <th className="text-right px-3 py-2.5 font-medium">净值</th>
                  <th className="text-right px-3 py-2.5 font-medium">折溢价</th>
                  <th className="text-right px-3 py-2.5 font-medium">成交额</th>
                  <th className="text-center px-3 py-2.5 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.code} className="border-t hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-2 font-mono text-xs">{item.code}</td>
                    <td className="px-3 py-2 truncate max-w-[200px]" title={item.name}>{item.name}</td>
                    <td className="px-3 py-2 text-right font-mono">{item.price}</td>
                    <td className="px-3 py-2 text-right font-mono text-muted-foreground">{item.nav}</td>
                    <td className={cn("px-3 py-2 text-right font-mono", premiumClass(item.premium_rate))}>
                      {item.premium_rate > 0 ? "+" : ""}{item.premium_rate}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-muted-foreground">{fmtAmt(item.amount)}</td>
                    <td className="px-3 py-2 text-center">
                      <button onClick={() => goAnalyze(item)}
                        className="text-xs px-2.5 py-1 rounded-md border border-primary/40 text-primary hover:bg-primary/10 transition-colors">
                        深度分析
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
