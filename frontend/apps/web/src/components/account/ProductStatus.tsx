/**
 * Product status summary — plan, validity, credits, and expiring-soon count.
 * Shown at the top of the account sub-pages (design §7.3 client product status).
 * Data is fetched on mount and re-fetched when `refreshKey` changes.
 */
import { useEffect, useState } from "react";
import { BrainCircuit, Crown, Database, Laptop, Loader2 } from "lucide-react";

import { ApiError } from "@/lib/api";
import { getMyCredits, getMyEntitlements, getPlans, type PlanEntitlements } from "@/lib/productApi";
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
  const [entitlements, setEntitlements] = useState<PlanEntitlements>({});
  const [planNames, setPlanNames] = useState<Record<string, string>>({});
  const [planOrder, setPlanOrder] = useState<string[]>([]);
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
        setEntitlements(ent.entitlements ?? {});
        // Guard against a malformed/empty response so the card never crashes.
        setAvailable(Number(credits.available ?? 0));
        setExpiringSoon(Number(credits.expiring_soon ?? 0));
        const orderedPlans = [...plans].sort((a, b) => a.sort_order - b.sort_order);
        setPlanNames(Object.fromEntries(orderedPlans.map((plan) => [plan.code, plan.name_zh])));
        setPlanOrder(orderedPlans.map((plan) => plan.code));
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
      icon: BrainCircuit,
      label: "AI 研究可用量",
      value: available.toLocaleString(),
      sub: expiringSoon > 0 ? `${expiringSoon.toLocaleString()} 将在 7 日内到期` : "套餐内研究用量",
    },
    {
      icon: Database,
      label: "Data Hub 月度用量",
      value: Number(entitlements["datahub.monthly_credits"] ?? 0).toLocaleString(),
      sub: "随当前套餐按月发放",
    },
    {
      icon: Laptop,
      label: "可授权设备",
      value: Number(entitlements["desktop.device_limit"] ?? 0).toLocaleString(),
      sub: "Desktop 设备上限",
    },
  ];
  const planIndex = planOrder.indexOf(planCode);
  const datasetGroups = entitlements["datahub.dataset_groups"];
  const datasets = Array.isArray(datasetGroups) ? datasetGroups.map(String) : [];
  const historyDays = Number(entitlements["datahub.history_depth_days"] ?? 0);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        {planIndex >= 0 && <span className="font-medium text-foreground">第 {planIndex + 1}/{planOrder.length} 档</span>}
        {datasets.length > 0 && <span>可用数据集：{datasets.join(" · ")}</span>}
        {historyDays > 0 && <span>历史数据：{historyDays.toLocaleString()} 天</span>}
      </div>
    </div>
  );
}
