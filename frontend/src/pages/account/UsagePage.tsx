/**
 * Usage page (design §7.2 /account/usage): today's Data Hub request consumption
 * against the plan's daily quota. GET /api/usage/me.
 */
import { useCallback, useEffect, useState } from "react";
import { Activity, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { AccountNav } from "@/components/layout/AccountNav";
import { ApiError } from "@/lib/api";
import { getMyUsage, type UsageResponse } from "@/lib/productApi";

export function UsagePage() {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setUsage(await getMyUsage());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载用量失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const pct = usage && usage.quota_daily > 0
    ? Math.min(100, Math.round((usage.consumed / usage.quota_daily) * 100))
    : 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <AccountNav />
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <Activity className="h-5 w-5 text-primary" /> 用量
          </h1>
          <p className="text-xs text-muted-foreground">今日 Data Hub 请求用量，按套餐每日配额计量</p>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            reload();
          }}
          className="rounded-lg p-2 hover:bg-muted"
          title="刷新"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      {loading ? (
        <div className="flex items-center py-10 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载用量…
        </div>
      ) : usage ? (
        <section className="rounded-xl border bg-card p-6">
          <div className="flex items-end justify-between">
            <div>
              <div className="text-xs text-muted-foreground">今日已用 / 配额</div>
              <div className="mt-1 text-2xl font-bold">
                {usage.consumed.toLocaleString()}{" "}
                <span className="text-base font-normal text-muted-foreground">
                  / {usage.quota_daily.toLocaleString()}
                </span>
              </div>
            </div>
            <div className="text-right text-sm text-muted-foreground">
              剩余 {usage.remaining.toLocaleString()}
              <div className="text-xs">UTC 日 {usage.day} 重置</div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={
                "h-full rounded-full " +
                (pct >= 90 ? "bg-destructive" : pct >= 70 ? "bg-amber-500" : "bg-primary")
              }
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{pct}% 已用</p>
        </section>
      ) : (
        <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">无法加载用量。</p>
      )}
    </div>
  );
}
