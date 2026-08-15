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

import { ApiError } from "@/lib/api";
import {
  createActivationCodes, createDataCreditCodes, formatPlanPrice, getDataCreditPacks, getPlans,
  type CreatedCodeItem, type DataCreditPack, type PlanView,
} from "@/lib/productApi";

export function OperationsPage() {
  const [planCode, setPlanCode] = useState("");
  const [plans, setPlans] = useState<PlanView[]>([]);
  const [months, setMonths] = useState(3);
  const [count, setCount] = useState(1);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedCodeItem[]>([]);
  const [packs, setPacks] = useState<DataCreditPack[]>([]);
  const [packCode, setPackCode] = useState("");

  useEffect(() => {
    Promise.all([getPlans(), getDataCreditPacks()]).then(([catalog, packCatalog]) => {
      const paid = catalog.filter((plan) => plan.code !== "free");
      setPlans(paid);
      setPlanCode((current) => current || paid[0]?.code || "");
      setPacks(packCatalog);
      setPackCode((current) => current || packCatalog[0]?.code || "");
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

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-bold">
          <KeyRound className="h-5 w-5 text-primary" /> 运营后台 · 激活码
        </h1>
        <p className="text-xs text-muted-foreground">生成套餐激活码。明文仅在此处显示一次，请立即复制保存。</p>
      </header>

      <section className="rounded-xl border bg-card p-5">
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
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">生成 Data Credit 积分包码</h2>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-muted-foreground">积分包<select aria-label="Data Credit 积分包" value={packCode} onChange={(event) => setPackCode(event.target.value)} className="mt-1 block rounded-md border bg-background px-2 py-2 text-sm">{packs.map((pack) => <option key={pack.code} value={pack.code}>{pack.name_zh}（¥{(pack.price_cny_fen / 100).toFixed(2)}）</option>)}</select></label>
          <button type="button" onClick={() => void createPackCodes()} disabled={creating || !packCode} className="inline-flex h-10 items-center gap-1 rounded-md bg-primary px-4 text-sm text-primary-foreground disabled:opacity-50"><Plus className="h-4 w-4" />生成积分包码</button>
        </div>
      </section>

      {created.length > 0 && (
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
