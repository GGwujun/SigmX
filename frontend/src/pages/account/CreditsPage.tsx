/**
 * Credits page — product credit balance + expiring-soon summary.
 * The immutable per-lot ledger view (design §4.2) will land with a dedicated
 * /api/credits/lots endpoint; for now this surfaces the balance summary and
 * points users to the existing Account page for the legacy transaction log.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { ProductStatus } from "@/components/layout/ProductStatus";
import { AccountNav } from "@/components/layout/AccountNav";

export function CreditsPage() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <AccountNav />
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">积分中心</h1>
          <p className="text-xs text-muted-foreground">套餐积分按月发放，月底到期；购买/补偿积分永久有效</p>
        </div>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="rounded-lg p-2 hover:bg-muted"
          title="刷新"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      <ProductStatus refreshKey={refreshKey} />

      <section className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
        <p>
          积分批次与到期明细将随积分流水接口一并上线。当前可在
          <Link to="/account" className="mx-1 text-primary underline">
            个人中心
          </Link>
          查看历史消费与退还记录。
        </p>
        <p className="mt-2">
          扣费规则：AlphaForge 报告 <code className="rounded bg-muted px-1">50</code> 积分 / 次，基金套利报告
          <code className="ml-1 rounded bg-muted px-1">20</code> 积分 / 次。失败自动退还，仅退一次。
        </p>
      </section>
    </div>
  );
}
