import { useEffect, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Activity, BadgeDollarSign, Database, FilePenLine, RotateCcw, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { getOperationsState, refundActivationOrder, updateOperationalContent, updateOperationalEndpoint, updateOperationalProduct, type OperationsState } from "@/lib/productApi";

export function OperationsGovernance() {
  const [state, setState] = useState<OperationsState | null>(null);
  const [form, setForm] = useState({ productCode: "desktop_pro", price: "26800", endpointCode: "market.daily", credits: "3", cost: "1", quality: "0.99", slot: "home.hero", title: "", href: "/query", orderId: "", reason: "" });
  const load = () => getOperationsState().then(value => { if (value?.metrics) setState(value); }).catch(() => toast.error("运营状态加载失败"));
  useEffect(() => { void load(); }, []);
  const value = (key: keyof typeof form) => ({ value: form[key], onChange: (event: ChangeEvent<HTMLInputElement>) => setForm(current => ({ ...current, [key]: event.target.value })) });
  const execute = async (operation: () => Promise<unknown>) => { if (form.reason.trim().length < 5) return toast.error("操作原因至少 5 个字符"); try { await operation(); toast.success("操作已完成并审计"); await load(); } catch { toast.error("操作失败"); } };

  return <section className="space-y-4">
    <div><h2 className="text-base font-semibold">产品运营控制台</h2><p className="mt-1 text-xs text-muted-foreground">个人产品的商品、接口、内容、激活码订单与成本治理。所有变更保留前后值和操作原因。</p></div>
    {state && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Desktop 研究用户" value={String(state.metrics.desktop_research_users)} icon={Activity} /><Metric label="Desktop 活跃会话" value={String(state.metrics.desktop_active_sessions)} icon={ShieldCheck} /><Metric label="数据调用收入" value={`¥${(state.metrics.usage_revenue_cny_fen / 100).toFixed(2)}`} icon={BadgeDollarSign} /><Metric label="估算毛利率" value={`${(state.metrics.gross_margin_rate * 100).toFixed(1)}%`} icon={Database} /></div>}
    <label className="block text-xs text-muted-foreground">本批操作原因（必填）<input aria-label="运营操作原因" {...value("reason")} placeholder="说明变更原因，至少 5 个字符" className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm" /></label>
    <div className="grid gap-4 xl:grid-cols-2">
      <OperationCard title="商品与价格" icon={BadgeDollarSign}><form onSubmit={(event) => { event.preventDefault(); void execute(() => updateOperationalProduct(form.productCode, { enabled: true, price_cny_fen: Number(form.price), reason: form.reason })); }} className="grid grid-cols-[1fr_120px_auto] gap-2"><input aria-label="商品代码" {...value("productCode")} className={FIELD} /><input aria-label="价格分" type="number" {...value("price")} className={FIELD} /><button className={ACTION}>保存</button></form><Rows items={state?.products.map(item => `${item.code} · ¥${(item.price_cny_fen / 100).toFixed(2)} · ${item.enabled ? "上架" : "下架"}`) ?? []} /></OperationCard>
      <OperationCard title="接口成本与质量" icon={Database}><form onSubmit={(event) => { event.preventDefault(); void execute(() => updateOperationalEndpoint(form.endpointCode, { enabled: true, credit_cost: Number(form.credits), unit_cost_cny_fen: Number(form.cost), quality_score: Number(form.quality), reason: form.reason })); }} className="grid grid-cols-5 gap-2"><input aria-label="接口代码" {...value("endpointCode")} className={`${FIELD} col-span-2`} /><input aria-label="积分价格" type="number" {...value("credits")} className={FIELD} /><input aria-label="单位成本" type="number" step="0.01" {...value("cost")} className={FIELD} /><button className={ACTION}>保存</button></form><Rows items={state?.endpoints.map(item => `${item.code} · ${item.credit_cost} Credit · 质量 ${(item.quality_score * 100).toFixed(1)}%`) ?? []} /></OperationCard>
      <OperationCard title="内容与增长位" icon={FilePenLine}><form onSubmit={(event) => { event.preventDefault(); void execute(() => updateOperationalContent(form.slot, { title: form.title, href: form.href, enabled: true, reason: form.reason })); }} className="grid grid-cols-[120px_1fr_1fr_auto] gap-2"><input aria-label="运营位" {...value("slot")} className={FIELD} /><input aria-label="运营标题" {...value("title")} className={FIELD} /><input aria-label="运营链接" {...value("href")} className={FIELD} /><button className={ACTION}>保存</button></form><Rows items={state?.content.map(item => `${item.slot} · ${item.title} · ${item.enabled ? "启用" : "停用"}`) ?? []} /></OperationCard>
      <OperationCard title="订单撤销 / 退款记录" icon={RotateCcw}><form onSubmit={(event: FormEvent) => { event.preventDefault(); void execute(() => refundActivationOrder(form.orderId, form.reason, crypto.randomUUID())); }} className="grid grid-cols-[1fr_auto] gap-2"><input aria-label="激活码订单 ID" {...value("orderId")} placeholder="仅 activation_code 订单" className={FIELD} /><button className={ACTION}>记录撤销</button></form><Rows items={state?.refunds.map(item => `${item.order_id} · ${item.status} · ${item.reason}`) ?? []} /></OperationCard>
    </div>
    {state && <div className="rounded-xl border bg-card p-4"><h3 className="text-sm font-semibold">不可变操作审计</h3><Rows items={state.audit.slice(-8).reverse().map(item => `${item.actor_id} · ${item.object_type}/${item.object_id} · ${item.reason}`)} /></div>}
  </section>;
}

function OperationCard({ title, icon: Icon, children }: { title: string; icon: typeof Activity; children: ReactNode }) { return <div className="rounded-xl border bg-card p-4"><h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Icon className="h-4 w-4 text-primary" />{title}</h3>{children}</div>; }
function Rows({ items }: { items: string[] }) { return <div className="mt-3 space-y-1 text-xs text-muted-foreground">{items.length ? items.map(item => <div key={item} className="rounded border px-2 py-1.5">{item}</div>) : <div>暂无记录</div>}</div>; }
function Metric({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Activity }) { return <div className="rounded-xl border bg-card p-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</div><div className="mt-2 text-xl font-semibold">{value}</div></div>; }
const FIELD = "min-w-0 rounded-md border bg-background px-2 py-2 text-xs outline-none focus:border-primary";
const ACTION = "rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90";
