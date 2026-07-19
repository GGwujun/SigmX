import { cn } from "@/lib/utils";
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";

interface CheckItem {
  layer: number;
  name: string;
  triggered: boolean;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  action: string;
}

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
  // Group by layer, show worst severity per layer
  const layerMap = new Map<number, CheckItem[]>();
  for (const c of checks) {
    const existing = layerMap.get(c.layer) || [];
    existing.push(c);
    layerMap.set(c.layer, existing);
  }

  const layers = Array.from(layerMap.entries()).sort(([a], [b]) => a - b);

  if (layers.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-center text-sm text-white/40">
        暂无风控检查数据
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/10">
        <h3 className="text-sm font-semibold text-white/80">8 层风控状态</h3>
      </div>
      <div className="divide-y divide-white/5">
        {layers.map(([layer, items]) => {
          const triggered = items.filter(c => c.triggered);
          const worst = triggered.length > 0
            ? triggered.reduce((a, b) =>
                (["critical", "warning", "info"].indexOf(a.severity) < ["critical", "warning", "info"].indexOf(b.severity) ? a : b))
            : null;
          const Icon = worst ? SEVERITY_ICON[worst.severity] || CheckCircle : CheckCircle;
          const color = worst ? SEVERITY_COLOR[worst.severity] || "text-green-400" : "text-green-400";

          return (
            <div key={layer} className="px-4 py-3 flex items-start gap-3">
              <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center">
                <Icon className={cn("h-4 w-4", color)} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/70">
                    L{layer}: {items[0]?.name || `Layer ${layer}`}
                  </span>
                  <span className={cn("text-xs font-medium", color)}>
                    {worst ? worst.severity.toUpperCase() : "PASS"}
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
