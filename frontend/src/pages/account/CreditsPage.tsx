/**
 * Credits page — credit lots (with expiry) + the immutable ledger.
 * GET /api/credits/lots + /api/credits/ledger. Monthly lots show their month-end
 * expiry; purchased/admin lots are permanent (design §4.2).
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { AccountPage } from "@/components/layout/AccountPage";
import { ProductStatus } from "@/components/layout/ProductStatus";
import { ApiError } from "@/lib/api";
import { getMyLedger, getMyLots, type CreditLot, type LedgerEntry } from "@/lib/productApi";
import { cn } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  monthly: "月度套餐积分",
  purchase: "购买",
  legacy_migration: "迁移",
  admin: "补偿",
  test: "测试",
};

const OP_LABEL: Record<string, string> = {
  grant: "发放",
  reserve: "预扣",
  settle: "结算",
  refund: "退还",
};

function shortDateTime(value?: string | null): string {
  if (!value) return "永久";
  return value.slice(0, 16).replace("T", " ");
}

export function CreditsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [lots, setLots] = useState<CreditLot[]>([]);
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const [l, e] = await Promise.all([getMyLots(), getMyLedger()]);
      setLots(l);
      setEntries(e);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "加载积分明细失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  return (
    <AccountPage>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">AI 研究额度</h1>
          <p className="text-xs text-muted-foreground">展示当前套餐包含的 AI 研究用量及到期规则</p>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            setRefreshKey((k) => k + 1);
          }}
          className="rounded-lg p-2 hover:bg-muted"
          title="刷新"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      <ProductStatus refreshKey={refreshKey} />

      {/* Credit lots */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">额度批次</h2>
        {loading ? (
          <div className="flex items-center py-6 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载批次…
          </div>
        ) : lots.length === 0 ? (
          <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
            暂无积分批次。开通套餐或购买积分后会在此显示。
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">来源</th>
                  <th className="px-4 py-2 text-right font-medium">剩余 / 总量</th>
                  <th className="px-4 py-2 text-left font-medium">到期</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot) => (
                  <tr key={lot.id} className="border-t">
                    <td className="px-4 py-2">{SOURCE_LABEL[lot.source] ?? lot.source}</td>
                    <td className="px-4 py-2 text-right font-mono">
                      <span className="font-medium">{lot.amount_remaining}</span>
                      <span className="text-muted-foreground"> / {lot.amount_total}</span>
                    </td>
                    <td className={cn("px-4 py-2", lot.expires_at ? "" : "text-muted-foreground")}>
                      {shortDateTime(lot.expires_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Ledger */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">流水记录</h2>
        {loading ? (
          <div className="flex items-center py-6 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载流水…
          </div>
        ) : entries.length === 0 ? (
          <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
            暂无流水。
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">类型</th>
                  <th className="px-4 py-2 text-right font-medium">变动</th>
                  <th className="px-4 py-2 text-left font-medium">时间</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-t">
                    <td className="px-4 py-2">{OP_LABEL[e.operation] ?? e.operation}</td>
                    <td
                      className={cn(
                        "px-4 py-2 text-right font-mono",
                        e.delta > 0 ? "text-emerald-600" : e.delta < 0 ? "text-red-600" : "",
                      )}
                    >
                      {e.delta > 0 ? "+" : ""}
                      {e.delta}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{shortDateTime(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-xl border bg-card p-5 text-xs text-muted-foreground">
        扣费规则：AlphaForge 报告 <code className="rounded bg-muted px-1">50</code> 积分 / 次，基金套利报告
        <code className="ml-1 rounded bg-muted px-1">20</code> 积分 / 次。失败自动退还，仅退一次。
      </section>
    </AccountPage>
  );
}
