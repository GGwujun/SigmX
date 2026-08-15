/**
 * Orders page (design §7.2 /account/orders) — the user's order history.
 * GET /api/orders. Mostly activation-code zero-value orders for now; the table
 * is generic so later payment-channel orders render unchanged.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, Receipt } from "lucide-react";
import { toast } from "sonner";

import { AccountNav } from "@/components/layout/AccountNav";
import { ApiError } from "@/lib/api";
import {
  getBillingSummary, getPlans, listOrders, type BillingSummary, type OrderItem,
} from "@/lib/productApi";

const STATUS_LABEL: Record<string, string> = {
  paid: "已支付",
  pending: "待支付",
  failed: "失败",
  refunded: "已退款",
};

function shortDateTime(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

function cny(fen: number): string {
  return `¥${(fen / 100).toFixed(2)}`;
}

export function OrdersPage() {
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [planNames, setPlanNames] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const [items, plans, billing] = await Promise.all([
        listOrders(), getPlans(), getBillingSummary(30),
      ]);
      setOrders(items);
      setPlanNames(Object.fromEntries(plans.map((plan) => [plan.code, plan.name_zh])));
      setSummary(billing);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载订单失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <AccountNav />
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <Receipt className="h-5 w-5 text-primary" /> 订单记录
          </h1>
          <p className="text-xs text-muted-foreground">套餐激活与购买的历史订单</p>
        </div>
        <button onClick={reload} className="rounded-lg p-2 hover:bg-muted" title="刷新">
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      {summary && (
        <section className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border bg-card p-4"><div className="text-xs text-muted-foreground">近 30 日实付</div><div className="mt-1 text-xl font-bold">{cny(summary.paid_cny_fen)}</div><div className="text-xs text-muted-foreground">{summary.paid_orders} 笔已支付订单</div></div>
          <div className="rounded-xl border bg-card p-4"><div className="text-xs text-muted-foreground">AI 研究消费</div><div className="mt-1 text-xl font-bold">{summary.research_credits_consumed.toLocaleString()}</div><div className="text-xs text-muted-foreground">{summary.research_credits_consumed.toLocaleString()} 研究积分</div></div>
          <div className="rounded-xl border bg-card p-4"><div className="text-xs text-muted-foreground">数据消费</div><div className="mt-1 text-xl font-bold">{summary.data_credits_consumed.toLocaleString()}</div><div className="text-xs text-muted-foreground">{summary.data_credits_consumed.toLocaleString()} Data Credit</div></div>
        </section>
      )}

      {loading ? (
        <div className="flex items-center py-10 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载订单…
        </div>
      ) : orders.length === 0 ? (
        <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
          暂无订单。在「套餐与激活」页输入激活码即可生成订单。
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left font-medium">套餐</th>
                <th className="px-4 py-2 text-left font-medium">状态</th>
                <th className="px-4 py-2 text-left font-medium">时长</th>
                <th className="px-4 py-2 text-right font-medium">金额</th>
                <th className="px-4 py-2 text-left font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t">
                  <td className="px-4 py-2">{planNames[o.plan_code] ?? o.plan_code}</td>
                  <td className="px-4 py-2">{STATUS_LABEL[o.status] ?? o.status}</td>
                  <td className="px-4 py-2">{o.months} 个月</td>
                  <td className="px-4 py-2 text-right font-mono">{cny(o.price_cny_fen)}</td>
                  <td className="px-4 py-2 text-muted-foreground">{shortDateTime(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
