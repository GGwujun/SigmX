import { cn } from "@/lib/utils";
import { CheckCircle, AlertTriangle, XCircle, MinusCircle } from "lucide-react";

interface CheckItem {
  layer: number;
  name: string;
  triggered: boolean;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  action: string;
}

// 固定 8 层骨架：即使后端没返回某层（无持仓/未触发）也照常显示，
// 避免出现"L8 空白"或空仓时整层消失让人误读为"缺失=没问题"。
const LAYER_DEFS: { layer: number; name: string }[] = [
  { layer: 1, name: "组合回撤熔断" },
  { layer: 2, name: "移动止盈" },
  { layer: 3, name: "ATR动态止损" },
  { layer: 4, name: "分级止盈" },
  { layer: 5, name: "防踩踏+指数熔断" },
  { layer: 6, name: "持仓天数" },
  { layer: 7, name: "跌停封板" },
  { layer: 8, name: "持仓相关性" },
];

const SEVERITY_ICON: Record<string, typeof CheckCircle> = {
  info: CheckCircle,
  warning: AlertTriangle,
  critical: XCircle,
};

const SEVERITY_COLOR: Record<string, string> = {
  info: "text-blue-400",
  warning: "text-yellow-400",
  critical: "text-red-400",
};

export function RiskMatrix({ checks }: { checks: CheckItem[] }) {
  // 按层聚合
  const layerMap = new Map<number, CheckItem[]>();
  for (const c of checks) {
    const existing = layerMap.get(c.layer) || [];
    existing.push(c);
    layerMap.set(c.layer, existing);
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/10">
        <h3 className="text-sm font-semibold text-white/80">8 层风控状态</h3>
      </div>
      <div className="divide-y divide-white/5">
        {LAYER_DEFS.map(({ layer, name }) => {
          const items = layerMap.get(layer) || [];
          const triggered = items.filter((c) => c.triggered);
          const worst = triggered.length > 0
            ? triggered.reduce((a, b) =>
                (["critical", "warning", "info"].indexOf(a.severity) < ["critical", "warning", "info"].indexOf(b.severity) ? a : b))
            : null;

          // 该层后端根本没返回 check（无持仓时 L2-L7，或持仓不足时 L8）
          const noData = items.length === 0;

          const Icon = worst ? SEVERITY_ICON[worst.severity] || CheckCircle : CheckCircle;
          const color = worst ? SEVERITY_COLOR[worst.severity] || "text-green-400" : "text-green-400";

          return (
            <div key={layer} className="px-4 py-3 flex items-start gap-3">
              <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center">
                {noData ? (
                  <MinusCircle className="h-4 w-4 text-white/25" />
                ) : (
                  <Icon className={cn("h-4 w-4", color)} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/70">
                    L{layer}: {name}
                  </span>
                  <span className={cn("text-xs font-medium", noData ? "text-white/30" : color)}>
                    {noData ? "无持仓·跳过" : worst ? worst.severity.toUpperCase() : "PASS"}
                  </span>
                </div>
                {worst && (
                  <div className="text-xs text-white/50 mt-1 truncate">{worst.message}</div>
                )}
                {triggered.length > 1 && (
                  <div className="text-xs text-white/40 mt-0.5">
                    +{triggered.length - 1} 条相关告警
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
