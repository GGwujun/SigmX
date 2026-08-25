/**
 * Subscription page — activate a plan code and see current plan state.
 * Uses POST /api/orders/activate (idempotent per request) + the ProductStatus
 * summary. The legacy credit-only redeem code stays on the existing Account page.
 */
import { useEffect, useState, type FormEvent } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { ProductStatus } from "@/components/layout/ProductStatus";
import { AccountPage } from "@/components/layout/AccountPage";
import { ApiError } from "@/lib/api";
import { activateCode, getPlans } from "@/lib/productApi";

export function SubscriptionPage() {
  const [code, setCode] = useState("");
  const [activating, setActivating] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [planNames, setPlanNames] = useState<Record<string, string>>({});

  useEffect(() => {
    getPlans()
      .then((plans) => setPlanNames(Object.fromEntries(plans.map((plan) => [plan.code, plan.name_zh]))))
      .catch(() => undefined);
  }, []);

  const doActivate = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim();
    if (!trimmed || activating) return;
    setActivating(true);
    try {
      // Idempotency key per attempt: the backend returns the same order if the
      // exact same key+code is replayed. Using a stable key per code prevents
      // accidental double-activation on a network retry.
      const idempotencyKey = `activation:${trimmed}`;
      const res = await activateCode(trimmed, idempotencyKey);
      if (res.replayed) {
        toast.info("该激活码此前已激活，未重复发放权益");
      } else {
        toast.success(
          `已开通 ${planNames[res.plan_code] ?? res.plan_code}（${res.months} 个月）` +
            (res.credits_granted ? `，获得 ${res.credits_granted} 积分` : ""),
        );
      }
      setCode("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "激活失败");
    } finally {
      setActivating(false);
    }
  };

  return (
    <AccountPage>
      <header>
        <h1 className="text-lg font-bold">套餐与激活</h1>
        <p className="text-xs text-muted-foreground">查看套餐状态、使用激活码开通或续期</p>
      </header>

      <ProductStatus refreshKey={refreshKey} />

      <section className="rounded-xl border bg-card p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <KeyRound className="h-4 w-4 text-primary" /> 激活套餐码
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          输入运营发放的套餐激活码（SX-XXXXXX-XXXXXX）。同一激活码只能使用一次，重复提交不会重复开通。
        </p>
        <form onSubmit={doActivate} className="mt-4 flex gap-2">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="SX-XXXXXX-XXXXXX"
            autoComplete="off"
            spellCheck={false}
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm font-mono uppercase tracking-wide outline-none focus:ring-2 focus:ring-primary/40"
          />
          <button
            type="submit"
            disabled={activating || !code.trim()}
            className="inline-flex h-10 items-center justify-center gap-1 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {activating ? <Loader2 className="h-4 w-4 animate-spin" /> : "激活套餐"}
          </button>
        </form>
      </section>
    </AccountPage>
  );
}
