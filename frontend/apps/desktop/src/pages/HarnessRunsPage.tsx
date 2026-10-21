import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Coins, Database, FileCheck2, ShieldCheck } from "lucide-react";

import { getHarnessRuns, type HarnessRun } from "@/lib/harnessApi";

const STATUS: Record<string, string> = { queued: "排队中", running: "运行中", succeeded: "已完成", failed: "失败", cancelled: "已取消" };
const TYPE: Record<string, string> = { research: "研究", backtest: "回测", screening: "选股", monitoring: "监控", swarm: "多智能体" };

export function HarnessRunsPage() {
  const [runs, setRuns] = useState<HarnessRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runType, setRunType] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    getHarnessRuns(100, { runType: runType || undefined, status: status || undefined })
      .then(items => { if (active) { setRuns(items); setError(""); } })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "运行记录加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [runType, status]);

  return <div className="mx-auto max-w-[1500px] space-y-5 p-5 lg:p-7">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Financial Harness</p><h1 className="mt-1 text-2xl font-semibold">运行中心</h1><p className="mt-1 text-sm text-muted-foreground">统一追踪研究、回测与自动化任务的证据、成本和治理边界。</p></div>
      <div className="flex gap-2">
        <select aria-label="运行类型" value={runType} onChange={e => setRunType(e.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm"><option value="">全部类型</option><option value="research">研究</option><option value="backtest">回测</option><option value="screening">选股</option></select>
        <select aria-label="运行状态" value={status} onChange={e => setStatus(e.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm"><option value="">全部状态</option><option value="running">运行中</option><option value="succeeded">已完成</option><option value="failed">失败</option></select>
      </div>
    </header>
    {loading && <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">正在读取权威运行账本…</div>}
    {error && <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><AlertTriangle className="h-4 w-4" />{error}</div>}
    {!loading && !error && runs.length === 0 && <div className="rounded-lg border border-dashed p-10 text-center"><Activity className="mx-auto h-7 w-7 text-muted-foreground" /><p className="mt-3 text-sm font-medium">暂无符合条件的运行</p><p className="mt-1 text-xs text-muted-foreground">从研究工作台、回测或监控任务发起一次运行。</p></div>}
    <div className="grid gap-4 xl:grid-cols-2">{runs.map(run => <RunCard key={run.run_id} run={run} />)}</div>
  </div>;
}

function RunCard({ run }: { run: HarnessRun }) {
  const cost = Object.entries(run.costs);
  return <article className="overflow-hidden rounded-lg border bg-card shadow-sm">
    <div className="flex items-start justify-between gap-3 border-b bg-muted/15 p-4"><div><div className="flex items-center gap-2"><span className="rounded border px-2 py-0.5 text-[11px] text-muted-foreground">{TYPE[run.run_type] || run.run_type}</span><span className="text-xs font-medium text-primary">{STATUS[run.status] || run.status}</span></div><h2 className="mt-2 font-semibold">{run.title}</h2><p className="mt-1 text-xs text-muted-foreground">{run.goal}</p></div><span className="font-mono text-[10px] text-muted-foreground">{run.run_id.slice(0, 10)}</span></div>
    <div className="grid grid-cols-3 border-b text-xs"><Metric icon={Activity} label="步骤" value={String(run.steps.length)} /><Metric icon={Database} label="证据" value={String(run.evidence.length)} /><Metric icon={Coins} label="成本" value={cost.length ? cost.map(([key, value]) => `${value} ${key === "data_credit" ? "Data Credit" : key}`).join(" · ") : "0"} /></div>
    <div className="grid gap-4 p-4 md:grid-cols-2"><section><h3 className="flex items-center gap-2 text-xs font-semibold"><FileCheck2 className="h-3.5 w-3.5 text-primary" />证据与产物</h3><div className="mt-2 space-y-2">{run.evidence.length ? run.evidence.slice(0, 3).map(item => <div key={item.id} className="rounded border p-2"><div className="text-xs font-medium">{item.title}</div><div className="mt-1 text-[11px] text-muted-foreground">{item.source}{item.data_version ? ` · ${item.data_version}` : ""}</div></div>) : <p className="text-xs text-muted-foreground">暂无证据记录</p>}</div></section><section><h3 className="flex items-center gap-2 text-xs font-semibold"><ShieldCheck className="h-3.5 w-3.5 text-primary" />治理与降级</h3><div className="mt-2 space-y-2 text-xs text-muted-foreground">{run.governance_events.map(item => <p key={item.id}>{item.level} · {item.decision} · {item.reason}</p>)}{run.degradations.map(item => <p key={item.id} className="text-warning">{item.code} · {item.message}</p>)}{!run.governance_events.length && !run.degradations.length && <p>运行未触发降级或额外治理事件</p>}</div></section></div>
  </article>;
}

function Metric({ icon: Icon, label, value }: { icon: typeof Activity; label: string; value: string }) { return <div className="border-r p-3 last:border-r-0"><div className="flex items-center gap-1.5 text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</div><div className="mt-1 truncate font-medium" title={value}>{value}</div></div>; }
