import { AlertTriangle, Cloud, Coins, Database, ShieldCheck } from "lucide-react";

import type { DataMode } from "@/lib/dataMode";
import type { HarnessRun, HarnessStatus } from "@/lib/harnessApi";

const GOVERNANCE_LABELS: Record<string, string> = {
  read: "只读", propose: "建议", simulate: "模拟", approve: "确认",
};

export function HarnessOverview({ status, runs, dataMode }: {
  status: HarnessStatus;
  runs: HarnessRun[];
  dataMode: DataMode;
}) {
  const connected = dataMode === "connected";
  return (
    <section className="rounded-md border bg-card shadow-sm shadow-black/[0.02]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/15 px-4 py-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-primary">Financial Harness</p>
          <h2 className="mt-0.5 text-base font-semibold">研究运行环境</h2>
        </div>
        <span className="rounded-full border px-2.5 py-1 text-xs font-medium">
          {connected ? "Connected · Data Hub" : "Standalone · 本地优先"}
        </span>
      </div>
      <div className="grid gap-3 p-4 md:grid-cols-4">
        <Status icon={Database} label="数据源" value={connected ? "Data Hub + 本地" : "本地数据"} />
        <Status icon={ShieldCheck} label="治理边界" value={`最高治理级别：${GOVERNANCE_LABELS[status.governance_ceiling] || status.governance_ceiling}`} />
        <Status icon={Coins} label="研究积分" value={String(status.research_credits)} />
        <Status icon={Cloud} label="Data Credits" value={String(status.data_credits)} />
      </div>
      {status.degradations.length > 0 && (
        <div className="mx-4 mb-4 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-muted-foreground">
          {status.degradations.map(item => <div key={item} className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" />{item}</div>)}
        </div>
      )}
      <div className="border-t px-4 py-3">
        <div className="mb-2 text-xs font-medium text-muted-foreground">最近 Harness Runs</div>
        {runs.length === 0 ? <p className="text-xs text-muted-foreground">暂无统一运行记录</p> : (
          <div className="grid gap-2 md:grid-cols-2">
            {runs.slice(0, 4).map(run => <div key={run.run_id} className="flex items-center justify-between rounded-md border px-3 py-2 text-xs"><span className="font-mono">{run.run_id}</span><span>{run.run_type} · {run.status}</span></div>)}
          </div>
        )}
      </div>
    </section>
  );
}

function Status({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: string }) {
  return <div className="rounded-md border bg-background p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5 text-primary" />{label}</div><div className="mt-2 text-sm font-semibold">{value}</div></div>;
}
