/**
 * Product status summary — plan, validity, credits, and expiring-soon count.
 * Shown at the top of the account sub-pages (design §7.3 client product status).
 * Data is fetched on mount and re-fetched when `refreshKey` changes.
 */
import { useEffect, useState } from "react";
import { Coins, Crown, Loader2, Timer } from "lucide-react";

import { ApiError } from "@/lib/api";
import { getMyCredits, getMyEntitlements, getPlans } from "@/lib/productApi";
import { cn } from "@/lib/utils";

function shortDate(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

export interface ProductStatusProps {
  /** Bump to force a re-fetch (e.g. after activating a code). */
  refreshKey?: number;
  className?: string;
}

export function ProductStatus({ refreshKey = 0, className }: ProductStatusProps) {
  const [planCode, setPlanCode] = useState<string>("free");
  const [validUntil, setValidUntil] = useState<string | null>(null);
  const [available, setAvailable] = useState<number>(0);
  const [expiringSoon, setExpiringSoon] = useState<number>(0);
  const [planNames, setPlanNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [ent, credits, plans] = await Promise.all([
          getMyEntitlements(), getMyCredits(), getPlans(),
        ]);
        if (cancelled) return;
        setPlanCode(ent.plan_code ?? "free");
        setValidUntil(ent.valid_until ?? null);
        // Guard against a malformed/empty response so the card never crashes.
        setAvailable(Number(credits.available ?? 0));
        setExpiringSoon(Number(credits.expiring_soon ?? 0));
        setPlanNames(Object.fromEntries(plans.map((plan) => [plan.code, plan.name_zh])));
      } catch (e) {
        // Non-fatal: the summary just stays at defaults. The owning page surfaces
        // its own errors for the actions that matter.
        if (!cancelled && e instanceof ApiError) {
          // keep defaults
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (loading) {
    return (
      <div className={cn("flex items-center justify-center py-6 text-muted-foreground", className)}>
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载账户状态…
      </div>
    );
  }

  const cards = [
    {
      icon: Crown,
      label: "当前套餐",
      value: planNames[planCode] ?? planCode,
      sub: validUntil ? `有效期至 ${shortDate(validUntil)}` : "永久 / 默认",
    },
    {
      icon: Coins,
      label: "可用积分",
      value: available.toLocaleString(),
      sub: "积分",
    },
    {
      icon: Timer,
      label: "即将到期",
      value: expiringSoon.toLocaleString(),
      sub: expiringSoon > 0 ? "7 日内到期，请尽快使用" : "无近期到期",
    },
  ];

  return (
    <div className={cn("grid gap-3 sm:grid-cols-3", className)}>
      {cards.map(({ icon: Icon, label, value, sub }) => (
        <div key={label} className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
          <div className="mt-1 text-xl font-bold">{value}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>
        </div>
      ))}
    </div>
  );
}
