/**
 * Operations console (design §7.2 /admin/operations) — generate plan activation
 * codes. Admin-only. Plaintext codes are shown exactly once at creation (the
 * store keeps only the hash, design §9); the operator must copy them.
 *
 * Legacy credit-only redeem codes keep their own page (/redeem-codes); this
 * console is for *plan* activation codes only (never infers a plan from credits).
 */
import { useEffect, useState, type FormEvent } from "react";
import { Copy, KeyRound, Loader2, Plus, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { OperationsGovernance } from "@/components/admin/OperationsGovernance";

import { ApiError } from "@/lib/api";
import {
  createActivationCodes, createDataCreditCodes, formatPlanPrice, getAdminProductMetrics,
  compensatePersonalCredits, revokePersonalSecurityTarget,
  getDataCreditPacks, getPlans, type AdminProductMetrics, type CreatedCodeItem,
  type DataCreditPack, type PlanView,
} from "@/lib/productApi";

export function OperationsPage({ view = "commerce" }: { view?: "dashboard" | "commerce" | "governance" | "support" }) {
  const [planCode, setPlanCode] = useState("");
  const [plans, setPlans] = useState<PlanView[]>([]);
  const [months, setMonths] = useState(3);
  const [count, setCount] = useState(1);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedCodeItem[]>([]);
  const [packs, setPacks] = useState<DataCreditPack[]>([]);
  const [packCode, setPackCode] = useState("");
  const [metrics, setMetrics] = useState<AdminProductMetrics | null>(null);
  const [supportAction, setSupportAction] = useState<"research" | "data" | "device" | "credential">("research");
  const [supportUserId, setSupportUserId] = useState("");
  const [supportTargetId, setSupportTargetId] = useState("");
  const [supportAmount, setSupportAmount] = useState(100);
  const [supportReason, setSupportReason] = useState("");

  useEffect(() => {
    Promise.all([getPlans(), getDataCreditPacks(), getAdminProductMetrics(30)]).then(([catalog, packCatalog, nextMetrics]) => {
      const paid = catalog.filter((plan) => plan.code !== "free");
      setPlans(paid);
      setPlanCode((current) => current || paid[0]?.code || "");
      setPacks(packCatalog);
      setPackCode((current) => current || packCatalog[0]?.code || "");
      setMetrics(nextMetrics);
    }).catch(() => toast.error("加载套餐目录失败"));
  }, []);

  const doCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (creating) return;
    setCreating(true);
    try {
      const codes = await createActivationCodes(planCode, months, count);
      setCreated((prev) => [...codes, ...prev]);
      toast.success(`已生成 ${codes.length} 个激活码（明文仅此一次展示）`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setCreating(false);
    }
  };

  const createPackCodes = async () => {
    if (!packCode || creating) return;
    setCreating(true);
    try {
      const codes = await createDataCreditCodes(packCode, count);
      setCreated((previous) => [...codes, ...previous]);
      toast.success(`已生成 ${codes.length} 个积分包激活码（明文仅此一次展示）`);
    } catch (error) { toast.error(error instanceof ApiError ? error.message : "生成失败"); }
    finally { setCreating(false); }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("已复制");
    } catch {
      toast.error("复制失败，请手动选择");
    }
  };

  const runSupportAction = async (event: FormEvent) => {
    event.preventDefault();
    if (creating) return;
    setCreating(true);
    try {
      if (supportAction === "research" || supportAction === "data") {
        await compensatePersonalCredits(supportUserId.trim(), supportAction, supportAmount, supportReason.trim());
      } else {
        await revokePersonalSecurityTarget(supportUserId.trim(), supportAction === "device" ? "devices" : "credentials", supportTargetId.trim(), supportReason.trim());
      }
      setSupportReason("");
      toast.success("个人支持操作已完成并写入审计日志");
    } catch (error) { toast.error(error instanceof ApiError ? error.message : "支持操作失败"); }
    finally { setCreating(false); }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-5 lg:p-8">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-bold">
          <KeyRound className="h-5 w-5 text-primary" /> {{ dashboard: "运营总览", commerce: "订单与兑换", governance: "套餐与商品", support: "客服工单" }[view]}
        </h1>
        <p className="text-xs text-muted-foreground">{{ dashboard: "经营指标、用户转化与 Data Hub 服务状态。", commerce: "管理订单和兑换码；新生成的明文仅展示一次。", governance: "管理商品、价格、接口成本与运营内容。", support: "处理用户额度补偿和安全撤销，所有操作永久审计。" }[view]}</p>
      </header>

      {view === "dashboard" && metrics && <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="周有效研究用户" value={metrics.weekly_effective_research_users.toLocaleString()} />
        <Metric label="近 30 日实付" value={`¥${(metrics.revenue_cny_fen / 100).toFixed(2)}`} detail={`${metrics.paid_orders} 笔订单`} />
        <Metric label="活跃 Data Hub Credential" value={metrics.active_datahub_credentials.toLocaleString()} />
        <Metric label="Data Hub 成功率" value={metrics.datahub_requests === 0 ? "暂无调用" : `${(metrics.datahub_success_rate * 100).toFixed(1)}%`} detail={`${metrics.datahub_requests} 次调用 · ${metrics.data_credits_charged} Data Credit`} />
      </section>}

      {view === "dashboard" && metrics && <section className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">个人用户转化漏斗 · 近 30 日</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {(["landing_view", "search_submitted", "result_view", "register_completed", "download_clicked", "checkout_intent"] as const).map((stage) => <Metric key={stage} label={({ landing_view: "访问首页", search_submitted: "发起搜索", result_view: "查看结果", register_completed: "完成注册", download_clicked: "下载 Desktop", checkout_intent: "购买意向" })[stage]} value={(metrics.personal_funnel?.[stage] ?? 0).toLocaleString()} />)}
        </div>
      </section>}

      {view === "governance" && <OperationsGovernance />}

      {view === "support" && <section className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">个人用户支持</h2>
        <p className="mt-1 text-xs text-muted-foreground">仅支持正向积分补偿和安全撤销；每次操作必须填写原因并永久审计。</p>
        <form onSubmit={runSupportAction} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-xs text-muted-foreground">操作<select aria-label="个人支持操作" value={supportAction} onChange={(event) => setSupportAction(event.target.value as typeof supportAction)} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm"><option value="research">补偿研究积分</option><option value="data">补偿 Data Credit</option><option value="device">撤销 Desktop 设备</option><option value="credential">撤销 Data Hub Credential</option></select></label>
          <label className="text-xs text-muted-foreground">个人用户 ID<input required value={supportUserId} onChange={(event) => setSupportUserId(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm" /></label>
          {(supportAction === "research" || supportAction === "data") ? <label className="text-xs text-muted-foreground">补偿数量<input aria-label="补偿数量" required type="number" min={1} max={1000000} value={supportAmount} onChange={(event) => setSupportAmount(Number(event.target.value))} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm" /></label> : <label className="text-xs text-muted-foreground">目标 ID<input aria-label="目标 ID" required value={supportTargetId} onChange={(event) => setSupportTargetId(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm" /></label>}
          <label className="text-xs text-muted-foreground">操作原因<input aria-label="操作原因" required minLength={5} value={supportReason} onChange={(event) => setSupportReason(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm" /></label>
          <button type="submit" disabled={creating} className="mt-4 h-10 rounded-md border px-4 text-sm font-medium hover:bg-muted disabled:opacity-50 sm:mt-auto">确认并审计</button>
        </form>
      </section>}

      {view === "commerce" && <section className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">生成激活码</h2>
        <form onSubmit={doCreate} className="mt-4 grid gap-3 sm:grid-cols-4">
          <label className="text-xs text-muted-foreground">
            套餐
            <select
              value={planCode}
              onChange={(e) => setPlanCode(e.target.value)}
              className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm"
            >
              {plans.map((plan) => (
                <option key={plan.code} value={plan.code}>
                  {plan.name_zh}（{formatPlanPrice(plan)}）
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            有效月数
            <input
              type="number"
              min={1}
              max={36}
              value={months}
              onChange={(e) => setMonths(Number(e.target.value) || 1)}
              className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            数量
            <input
              type="number"
              min={1}
              max={100}
              value={count}
              onChange={(e) => setCount(Number(e.target.value) || 1)}
              className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={creating || !planCode}
            className="mt-4 inline-flex h-10 items-center justify-center gap-1 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 sm:mt-auto"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            生成
          </button>
        </form>
      </section>}

      {view === "commerce" && <section className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">生成 Data Credit 积分包码</h2>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-muted-foreground">积分包<select aria-label="Data Credit 积分包" value={packCode} onChange={(event) => setPackCode(event.target.value)} className="mt-1 block rounded-md border bg-background px-2 py-2 text-sm">{packs.map((pack) => <option key={pack.code} value={pack.code}>{pack.name_zh}（¥{(pack.price_cny_fen / 100).toFixed(2)}）</option>)}</select></label>
          <button type="button" onClick={() => void createPackCodes()} disabled={creating || !packCode} className="inline-flex h-10 items-center gap-1 rounded-md bg-primary px-4 text-sm text-primary-foreground disabled:opacity-50"><Plus className="h-4 w-4" />生成积分包码</button>
        </div>
      </section>}

      {view === "commerce" && created.length > 0 && (
        <section className="rounded-xl border bg-card p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-600">
            <ShieldAlert className="h-4 w-4" /> 新生成的激活码（仅此一次可见）
          </div>
          <ul className="space-y-2">
            {created.map((c) => (
              <li
                key={c.code_hash}
                className="flex items-center justify-between gap-2 rounded-md border bg-background px-3 py-2"
              >
                <code className="font-mono text-sm tracking-wide">{c.plaintext}</code>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>
                    {c.plan_code}{c.months > 0 ? ` · ${c.months} 月` : " · Data Credit 积分包"}
                  </span>
                  <button
                    onClick={() => copy(c.plaintext)}
                    className="inline-flex items-center gap-1 rounded border px-2 py-1 hover:bg-muted"
                  >
                    <Copy className="h-3 w-3" /> 复制
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="rounded-xl border bg-card p-4"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-xl font-bold">{value}</div>{detail && <div className="text-xs text-muted-foreground">{detail}</div>}</div>;
}
