/**
 * Public pricing page — server-driven plan comparison (design §7.1 /pricing).
 * Pulls the catalog from GET /api/catalog/plans; never hard-codes prices.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Loader2 } from "lucide-react";

import { ApiError } from "@/lib/api";
import { formatPlanPrice, getPlans, type PlanView } from "@/lib/productApi";
import { cn } from "@/lib/utils";
import { trackPersonalFunnel } from "@/lib/personalFunnel";
import { isAuthenticated } from "@/lib/apiAuth";

// Human labels for the stable entitlement keys (design §6). Keys themselves are
// stable; only the display label is localized here.
const ENTITLEMENT_LABELS: Record<string, string> = {
  "datahub.enabled": "Data Hub",
  "datahub.dataset_groups": "数据集权限",
  "datahub.monthly_credits": "每月 Data Credit",
  "datahub.rate_limit_per_minute": "每分钟调用",
  "datahub.concurrent_limit": "并发请求",
  "datahub.max_rows_per_request": "单次最大行数",
  "datahub.history_depth_days": "历史数据深度",
  "datahub.commercial_use": "商业使用",
  "desktop.connected_mode": "桌面端 Connected 模式",
  "desktop.device_limit": "设备数",
  "cloud_ai.enabled": "云端 AI",
  "cloud_ai.concurrent_jobs": "云端 AI 并发",
  "reports.cloud_history": "云端报告历史",
};

function quotaLabel(key: string, value: number | boolean | string[]): string {
  if (Array.isArray(value)) return value.length > 0 ? value.join("、") : "合同配置";
  if (typeof value === "boolean") return value ? "✓" : "—";
  if (key === "datahub.monthly_credits") return `${value.toLocaleString()} 分/月`;
  if (key === "datahub.rate_limit_per_minute") return value > 0 ? `${value.toLocaleString()} 次/分` : "合同配置";
  if (key === "datahub.concurrent_limit") return value > 0 ? `${value} 个` : "合同配置";
  if (key === "datahub.max_rows_per_request") return value > 0 ? `${value.toLocaleString()} 行` : "合同配置";
  if (key === "datahub.history_depth_days") return value > 0 ? `${value.toLocaleString()} 天` : "合同配置";
  if (key === "desktop.device_limit") return `${value} 台`;
  if (key === "cloud_ai.concurrent_jobs") return `${value} 个`;
  return String(value);
}

export function PricingPage() {
  const signedIn = isAuthenticated();
  const [plans, setPlans] = useState<PlanView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackPersonalFunnel("pricing_view");
    let cancelled = false;
    (async () => {
      try {
        const data = await getPlans();
        if (!cancelled) setPlans(data);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "无法加载套餐目录");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 加载套餐…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-muted-foreground">
        <p>{error}</p>
        <Link to="/login" className="text-primary underline">
          返回登录
        </Link>
      </div>
    );
  }

  // Collect the union of entitlement keys across plans for the comparison rows.
  const allKeys = Array.from(
    new Set(plans.flatMap((p) => Object.keys(p.entitlements))),
  ).filter((k) => ENTITLEMENT_LABELS[k]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight">选择适合你的套餐</h1>
        <p className="mt-2 text-muted-foreground">
          所有价格与额度由服务端目录驱动，可在账户中心用激活码开通。
        </p>
      </header>

      <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {plans.map((plan) => {
          const featured = plan.code === "pro_bundle";
          return (
            <div
              key={plan.code}
              className={cn(
                "flex flex-col rounded-xl border p-6 shadow-sm",
                featured && "border-primary ring-2 ring-primary/20",
              )}
            >
              <h2 className="text-lg font-semibold">{plan.name_zh}</h2>
              <p className="mt-1 min-h-[2.5rem] text-sm text-muted-foreground">
                {plan.description}
              </p>
              <div className="mt-4 text-2xl font-bold">{formatPlanPrice(plan)}</div>

              <ul className="mt-6 flex-1 space-y-2 text-sm">
                {allKeys.map((key) => {
                  const val = plan.entitlements[key];
                  const present = val !== undefined;
                  return (
                    <li key={key} className="flex items-center justify-between gap-2">
                      <span className="text-muted-foreground">{ENTITLEMENT_LABELS[key]}</span>
                      <span className={cn("font-medium", !present && "text-muted-foreground/40")}>
                        {present ? (
                          typeof val === "boolean" && val ? (
                            <Check className="h-4 w-4 text-primary" />
                          ) : typeof val === "boolean" ? (
                            "—"
                          ) : (
                            quotaLabel(key, val)
                          )
                        ) : (
                          "—"
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>

              <Link
                to={signedIn ? "/account/subscription" : "/register"}
                onClick={() => { if (plan.code !== "free") trackPersonalFunnel("checkout_intent"); }}
                className={cn(
                  "mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90",
                )}
              >
                {signedIn ? "管理套餐" : "注册体验"}
              </Link>
            </div>
          );
        })}
      </section>
    </div>
  );
}
