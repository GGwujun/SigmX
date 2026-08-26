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
  const sortedPlans = [...plans].sort((a, b) => a.sort_order - b.sort_order);
  const allKeys = Array.from(
    new Set(plans.flatMap((p) => Object.keys(p.entitlements))),
  ).filter((k) => ENTITLEMENT_LABELS[k]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight">从体验到专业研究，权益逐级增加</h1>
        <p className="mt-2 text-muted-foreground">
          每一档都包含上一档全部能力，只提升研究规模、数据范围和协作效率。
        </p>
      </header>

      <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {sortedPlans.map((plan, index) => {
          const featured = plan.code === "data_developer";
          const highest = plan.code === "pro_bundle";
          return (
            <div
              key={plan.code}
              className={cn(
                "flex flex-col rounded-xl border p-6 shadow-sm",
                featured && "border-primary ring-2 ring-primary/20",
              )}
            >
              <div className="flex min-h-6 items-center justify-between gap-2">
                <span className="text-xs font-medium text-muted-foreground">第 {index + 1} 档</span>
                {featured && <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">进阶推荐</span>}
                {highest && <span className="rounded-full bg-foreground px-2 py-0.5 text-xs text-background">最高配置</span>}
              </div>
              <h2 className="mt-2 text-lg font-semibold">{plan.name_zh}</h2>
              <p className="mt-1 min-h-[2.5rem] text-sm text-muted-foreground">
                {plan.description}
              </p>
              <div className="mt-4 text-2xl font-bold">{formatPlanPrice(plan)}</div>
              {index > 0 && <p className="mt-3 text-xs font-medium text-primary">包含上一档全部权益</p>}

              <ul className="mt-6 flex-1 space-y-3 text-sm">
                <li className="flex justify-between gap-2"><span className="text-muted-foreground">AI 研究/月</span><strong>{plan.monthly_credits.toLocaleString()}</strong></li>
                <li className="flex justify-between gap-2"><span className="text-muted-foreground">Data Hub/月</span><strong>{quotaLabel("datahub.monthly_credits", plan.entitlements["datahub.monthly_credits"] ?? 0)}</strong></li>
                <li className="flex justify-between gap-2"><span className="text-muted-foreground">设备</span><strong>{quotaLabel("desktop.device_limit", plan.entitlements["desktop.device_limit"] ?? 0)}</strong></li>
                <li className="flex items-start justify-between gap-2"><span className="text-muted-foreground">数据集</span><strong className="text-right text-xs">{quotaLabel("datahub.dataset_groups", plan.entitlements["datahub.dataset_groups"] ?? [])}</strong></li>
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

      <section className="mt-12 overflow-hidden rounded-xl border bg-card">
        <div className="border-b px-5 py-4"><h2 className="font-semibold">完整权益对比</h2><p className="text-xs text-muted-foreground">后一档完整包含前一档权益</p></div>
        <div className="overflow-x-auto">
          <table aria-label="完整权益对比" className="w-full min-w-[820px] text-sm">
            <thead><tr className="border-b bg-muted/30"><th className="px-4 py-3 text-left">权益</th>{sortedPlans.map(plan => <th key={plan.code} className="px-4 py-3 text-center">{plan.name_zh}</th>)}</tr></thead>
            <tbody>
              <tr className="border-b"><td className="px-4 py-3 text-muted-foreground">AI 研究月度用量</td>{sortedPlans.map(plan => <td key={plan.code} className="px-4 py-3 text-center font-medium">{plan.monthly_credits.toLocaleString()}</td>)}</tr>
              {allKeys.map(key => <tr key={key} className="border-b last:border-0"><td className="px-4 py-3 text-muted-foreground">{ENTITLEMENT_LABELS[key]}</td>{sortedPlans.map(plan => { const val = plan.entitlements[key]; return <td key={plan.code} className="px-4 py-3 text-center font-medium">{typeof val === "boolean" ? (val ? <Check className="mx-auto h-4 w-4 text-primary" /> : "—") : val === undefined ? "—" : quotaLabel(key, val)}</td>; })}</tr>)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
