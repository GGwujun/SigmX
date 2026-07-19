import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface IndexData {
  code: string;
  name: string;
  close: number;
  change_pct: number;
}

interface SectorItem {
  name: string;
  change_pct: number;
  amount?: number;
}

interface FundItem {
  code: string;
  name: string;
  premium_rate: number;
  price: number;
  nav: number;
  amount: number;
  type: string;
}

function premiumColor(rate: number): string {
  if (rate >= 8) return "bg-red-600";
  if (rate >= 5) return "bg-red-500";
  if (rate >= 2) return "bg-red-400/70";
  if (rate > 0) return "bg-red-400/40";
  if (rate <= -8) return "bg-green-600";
  if (rate <= -5) return "bg-green-500";
  if (rate <= -2) return "bg-green-400/70";
  if (rate < 0) return "bg-green-400/40";
  return "bg-white/10";
}

function IndexCard({ data }: { data: IndexData }) {
  const up = data.change_pct >= 0;
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="text-xs text-white/40 mb-1">{data.name}</div>
      <div className={cn("text-2xl font-bold font-mono", up ? "text-red-400" : "text-green-400")}>
        {data.close.toFixed(2)}
      </div>
      <div className={cn("text-sm font-mono mt-1", up ? "text-red-400" : "text-green-400")}>
        {up ? "+" : ""}{data.change_pct.toFixed(2)}%
      </div>
    </div>
  );
}

function SectorHeatmap({ sectors }: { sectors: SectorItem[] }) {
  if (!sectors.length) return null;
  const maxAbs = Math.max(...sectors.map(s => Math.abs(s.change_pct)), 1);
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="text-xs text-white/40 mb-3">板块热力图</div>
      <div className="grid grid-cols-6 gap-1">
        {sectors.map((s) => {
          const intensity = Math.min(1, Math.abs(s.change_pct) / maxAbs);
          const up = s.change_pct >= 0;
          const bg = up
            ? `rgba(239, 68, 68, ${0.2 + intensity * 0.6})`
            : `rgba(34, 197, 94, ${0.2 + intensity * 0.6})`;
          return (
            <div
              key={s.name}
              className="rounded px-2 py-3 text-center"
              style={{ background: bg }}
            >
              <div className="text-xs text-white/90 font-medium truncate">{s.name}</div>
              <div className={cn("text-xs font-mono mt-0.5", up ? "text-white" : "text-white/80")}>
                {up ? "+" : ""}{s.change_pct.toFixed(2)}%
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PremiumBoard({ funds }: { funds: FundItem[] }) {
  if (!funds.length) return null;
  const sorted = [...funds].sort((a, b) => Math.abs(b.premium_rate) - Math.abs(a.premium_rate));
  const topPremium = sorted.filter(f => f.premium_rate > 0).slice(0, 8);
  const topDiscount = sorted.filter(f => f.premium_rate < 0).slice(0, 8);

  const renderTable = (items: FundItem[], title: string, emoji: string) => (
    <div className="flex-1">
      <div className="text-xs text-white/40 mb-2">{emoji} {title}</div>
      <div className="space-y-0.5">
        {items.map((f) => (
          <div key={f.code} className={cn("flex items-center justify-between px-2 py-1.5 rounded text-xs",
            premiumColor(f.premium_rate))}>
            <span className="text-white/90 font-medium">{f.name}</span>
            <span className="font-mono text-white font-bold">
              {f.premium_rate > 0 ? "+" : ""}{f.premium_rate.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4 flex gap-4">
      {renderTable(topPremium, "溢价 TOP", "📈")}
      <div className="w-px bg-white/10" />
      {renderTable(topDiscount, "折价 TOP", "📉")}
    </div>
  );
}

function ClockDisplay() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const timeStr = now.toLocaleTimeString("zh-CN", { hour12: false });
  const dateStr = now.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", weekday: "short" });
  return (
    <div className="text-right">
      <div className="text-3xl font-bold font-mono text-white/90">{timeStr}</div>
      <div className="text-xs text-white/40 mt-1">{dateStr}</div>
    </div>
  );
}

export default function BigScreen() {
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [sectors, setSectors] = useState<SectorItem[]>([]);
  const [premiumFunds, setPremiumFunds] = useState<FundItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [indicesRes, sectorsRes, fundsRes] = await Promise.all([
        // 后端暂无 getMarketIndices/getSectorRanking 独立接口 → 降级为空，UI 区块隐藏
        Promise.resolve([]),
        Promise.resolve([]),
        api.scanFunds?.("all", 0, 1, 50, "premium_abs", "") ?? Promise.resolve({ items: [] }),
      ]);
      if (Array.isArray(indicesRes)) setIndices(indicesRes);
      if (Array.isArray(sectorsRes)) setSectors(sectorsRes);
      if (fundsRes?.items) setPremiumFunds(fundsRes.items);
    } catch (e) {
      console.error("BigScreen load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  // Auto-refresh every 60s
  useEffect(() => {
    const t = setInterval(loadData, 60000);
    return () => clearInterval(t);
  }, [loadData]);

  // Compute summary stats
  const stats = useMemo(() => {
    const upIndices = indices.filter(i => i.change_pct >= 0).length;
    const topPremium = premiumFunds.filter(f => f.premium_rate > 0).length;
    const topDiscount = premiumFunds.filter(f => f.premium_rate < 0).length;
    return { upIndices, totalIndices: indices.length, topPremium, topDiscount };
  }, [indices, premiumFunds]);

  return (
    <div className="h-screen w-screen bg-[#0a0a0a] text-white overflow-hidden p-4 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold text-white/80">SigmX 市场大屏</h1>
          {stats.totalIndices > 0 && (
            <span className="text-xs text-white/40">
              {stats.upIndices}/{stats.totalIndices} 指数上涨 ·
              {stats.topPremium} 溢价 · {stats.topDiscount} 折价
            </span>
          )}
        </div>
        <ClockDisplay />
      </header>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-white/40">加载中…</div>
      ) : (
        <div className="flex-1 grid grid-cols-12 grid-rows-6 gap-3 min-h-0">
          {/* 指数卡片 — row 1 */}
          <div className="col-span-12 row-span-1 grid grid-cols-5 gap-3">
            {indices.slice(0, 5).map((idx) => (
              <IndexCard key={idx.code} data={idx} />
            ))}
          </div>

          {/* 板块热力图 — row 2-4, col 1-8 */}
          <div className="col-span-8 row-span-3">
            <SectorHeatmap sectors={sectors} />
          </div>

          {/* 折溢价排行 — row 2-4, col 9-12 */}
          <div className="col-span-4 row-span-3">
            <PremiumBoard funds={premiumFunds} />
          </div>

          {/* 底部留白区 — row 5-6, 可放更多信息 */}
          <div className="col-span-12 row-span-2 rounded-lg bg-white/5 border border-white/10 p-4">
            <div className="text-xs text-white/40 mb-2">市场速览</div>
            <div className="grid grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-white/40">上证指数</span>
                <span className={cn("ml-2 font-mono font-bold",
                  (indices[0]?.change_pct ?? 0) >= 0 ? "text-red-400" : "text-green-400")}>
                  {indices[0] ? `${indices[0].close.toFixed(2)} (${indices[0].change_pct >= 0 ? "+" : ""}${indices[0].change_pct.toFixed(2)}%)` : "--"}
                </span>
              </div>
              <div>
                <span className="text-white/40">最高溢价</span>
                <span className="ml-2 font-mono font-bold text-red-400">
                  {premiumFunds.length > 0
                    ? `${Math.max(...premiumFunds.map(f => f.premium_rate)).toFixed(2)}%`
                    : "--"}
                </span>
              </div>
              <div>
                <span className="text-white/40">最大折价</span>
                <span className="ml-2 font-mono font-bold text-green-400">
                  {premiumFunds.length > 0
                    ? `${Math.min(...premiumFunds.map(f => f.premium_rate)).toFixed(2)}%`
                    : "--"}
                </span>
              </div>
              <div>
                <span className="text-white/40">活跃板块</span>
                <span className="ml-2 text-white/80">
                  {sectors.length > 0 ? sectors[0]?.name : "--"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
