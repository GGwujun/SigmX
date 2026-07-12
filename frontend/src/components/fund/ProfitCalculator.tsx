import { useState, useRef, useEffect } from "react";
import { X, Calculator } from "lucide-react";
import { cn } from "@/lib/utils";

interface ProfitCalculatorProps {
  nav: number;
  price: number;
  premiumRate: number;
  fundType: string;
}

const FEE_TABLE: Record<string, { purchaseFee: number; sellFee: number; label: string }> = {
  ETF: { purchaseFee: 0.005, sellFee: 0.001, label: "ETF" },
  LOF: { purchaseFee: 0.012, sellFee: 0.001, label: "LOF" },
  QDII: { purchaseFee: 0.015, sellFee: 0.001, label: "QDII" },
};

const HOLD_OPTIONS = [
  { days: 1, redeemFee: 0.015, label: "<7天 (1.5%)" },
  { days: 7, redeemFee: 0.005, label: "≥7天 (0.5%)" },
  { days: 30, redeemFee: 0.0025, label: "≥30天 (0.25%)" },
  { days: 365, redeemFee: 0, label: "≥1年 (0%)" },
];

export function ProfitCalculator({ nav, price, premiumRate, fundType }: ProfitCalculatorProps) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(100000);
  const [holdIdx, setHoldIdx] = useState(1);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fees = FEE_TABLE[fundType] || FEE_TABLE.LOF;
  const hold = HOLD_OPTIONS[holdIdx];

  // Calculation
  const purchaseFee = amount * fees.purchaseFee;
  const actualInvest = amount - purchaseFee;
  const shares = nav > 0 ? actualInvest / nav : 0;
  const sellValue = shares * price * (1 - fees.sellFee);
  const redeemFee = sellValue * hold.redeemFee;
  const netProfit = sellValue - amount - redeemFee;
  const profitRate = amount > 0 ? (netProfit / amount) * 100 : 0;

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={cn("p-1 rounded transition-colors", open ? "text-primary bg-primary/10" : "text-muted-foreground hover:text-primary")}
        title="利润计算器"
      >
        <Calculator className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-72 rounded-lg border bg-card shadow-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">套利利润计算</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1">
              <span className="text-[10px] text-muted-foreground">投资金额 (元)</span>
              <input type="number" value={amount} onChange={e => setAmount(Number(e.target.value) || 0)}
                className="px-2 py-1 rounded border bg-background text-sm font-mono" />
            </label>
            <label className="grid gap-1">
              <span className="text-[10px] text-muted-foreground">持有期限</span>
              <select value={holdIdx} onChange={e => setHoldIdx(Number(e.target.value))}
                className="px-2 py-1 rounded border bg-background text-sm">
                {HOLD_OPTIONS.map((h, i) => <option key={i} value={i}>{h.label}</option>)}
              </select>
            </label>
          </div>

          <div className="text-xs space-y-1 border-t pt-2">
            <div className="flex justify-between"><span className="text-muted-foreground">申购费 ({(fees.purchaseFee * 100).toFixed(1)}%)</span><span className="font-mono">-{purchaseFee.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">获得份额</span><span className="font-mono">{shares.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">卖出金额</span><span className="font-mono">{sellValue.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">赎回费 ({(hold.redeemFee * 100).toFixed(2)}%)</span><span className="font-mono">-{redeemFee.toFixed(2)}</span></div>
          </div>

          <div className={cn("text-center py-2 rounded-lg font-medium",
            netProfit > 0 ? "bg-green-500/10 text-green-600 dark:text-green-400" : "bg-red-500/10 text-red-500")}>
            <div className="text-lg font-mono">{netProfit > 0 ? "+" : ""}{netProfit.toFixed(2)} 元</div>
            <div className="text-xs">利润率 {profitRate > 0 ? "+" : ""}{profitRate.toFixed(2)}%</div>
          </div>

          <div className="text-[10px] text-muted-foreground text-center">
            基于当前价 {price} / 净值 {nav} · 溢价率 {premiumRate > 0 ? "+" : ""}{premiumRate}%
          </div>
        </div>
      )}
    </div>
  );
}
