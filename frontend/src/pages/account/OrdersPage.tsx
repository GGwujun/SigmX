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
import { listOrders, type OrderItem } from "@/lib/productApi";

const STATUS_LABEL: Record<string, string> = {
  paid: "已支付",
  pending: "待支付",
  failed: "失败",
  refunded: "已退款",
};

const PLAN_NAME_ZH: Record<string, string> = {
  free: "免费版",
  advanced: "进阶版",
  pro: "专业版",
};

function shortDateTime(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function OrdersPage() {
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setOrders(await listOrders());
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
                <th className="px-4 py-2 text-left font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t">
                  <td className="px-4 py-2">{PLAN_NAME_ZH[o.plan_code] ?? o.plan_code}</td>
                  <td className="px-4 py-2">{STATUS_LABEL[o.status] ?? o.status}</td>
                  <td className="px-4 py-2">{o.months} 个月</td>
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
