import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  Download,
  FileDown,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  XCircle,
  Zap,
} from "lucide-react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { api, type AlphaForgeReportDetail, type AlphaForgeReportItem, type AlphaForgeRunDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

const SIGNAL_COLORS: Record<string, string> = {
  BUY: "text-success bg-success/10",
  SELL: "text-danger bg-danger/10",
  HOLD: "text-warning bg-warning/10",
  "买入": "text-success bg-success/10",
  "卖出": "text-danger bg-danger/10",
  "持有": "text-warning bg-warning/10",
  "减持": "text-danger bg-danger/10",
};

const AGENT_LABELS: Record<string, string> = {
  data_collector: "数据采集",
  technical_analyst: "技术分析",
  sentiment_analyst: "情绪分析",
  news_analyst: "新闻舆情",
  fundamental_analyst: "基本面",
  policy_analyst: "政策分析",
  capital_flow_analyst: "资金追踪",
  lockup_analyst: "解禁监控",
  global_market_analyst: "全球市场",
  quality_gate: "质量门控",
  bull_case: "多方论证",
  bear_case: "空方论证",
  bull_rebuttal: "多方反驳",
  bear_rebuttal: "空方反驳",
  neutral_synthesis: "中立综合",
  trader: "交易决策",
  risk_officer: "风控评估",
  portfolio_manager: "最终裁决",
  report_writer: "报告生成",
};

const TASK_STATUS_ICONS: Record<string, typeof Play> = {
  pending: Clock,
  waiting: Clock,
  in_progress: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  blocked: AlertTriangle,
  cancelled: XCircle,
};

const REPORT_SECTIONS = ["投资结论", "核心逻辑", "多方观点", "空方观点", "风险清单", "交易计划", "证据摘要"];

const MARKET_LABELS: Record<string, string> = {
  "A-shares": "A 股",
  "Hong Kong": "港股",
  US: "美股",
  crypto: "加密货币",
};

function signalBadge(signal: string) {
  const color = SIGNAL_COLORS[signal] || "text-muted-foreground bg-muted";
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold", color)}>
      {signal || "暂无"}
    </span>
  );
}

function qualityBadge(report: Pick<AlphaForgeReportItem, "report_quality">) {
  const quality = report.report_quality || "unknown";
  if (quality === "ok") {
    return <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">数据正常</span>;
  }
  if (quality === "unreliable") {
    return <span className="rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">数据不可信</span>;
  }
  if (quality === "degraded") {
    return <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">数据存疑</span>;
  }
  return <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">未校验</span>;
}

function statusLabel(status?: string | null): string {
  switch (status) {
    case "pending": return "等待中";
    case "waiting": return "等待上游";
    case "in_progress": return "执行中";
    case "completed": return "已完成";
    case "failed": return "失败";
    case "blocked": return "已阻塞";
    case "cancelled": return "已取消";
    case "running": return "运行中";
    case "success": return "成功";
    default: return status || "暂无状态";
  }
}

type AlphaForgeTask = AlphaForgeRunDetail["tasks"][number];

function taskDisplayStatus(task: AlphaForgeTask): string {
  if (task.display_status) return task.display_status;
  if (task.status === "blocked" && (task.blocked_by?.length ?? 0) > 0 && !task.error) return "waiting";
  return task.status;
}

function taskDisplayLabel(task: AlphaForgeTask): string {
  return task.display_status_label || statusLabel(taskDisplayStatus(task));
}

function isTaskDone(task: AlphaForgeTask): boolean {
  return task.status === "completed";
}

function shortDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "暂无日期";
}

function terminalStatus(status?: string | null): boolean {
  return ["completed", "failed", "cancelled"].includes(status || "");
}

/**
 * Normalize agent-generated markdown so tables render correctly.
 *
 * LLM reports often emit a table immediately after a heading or paragraph
 * with NO blank line between them:
 *   ### 1.1 辩论评分总览
 *   | 辩论方 | 核心论据 |
 *   |--------|---------|
 *
 * Standard Markdown + GFM require a blank line before a table, otherwise the
 * whole thing is parsed as a single paragraph (the "1.1 辩论评分总览 | 辩论方..."
 * rendering bug). This inserts a blank line before any line that starts a GFM
 * table (a `|` row followed by a `|---|` separator) when the previous line is
 * non-empty. Also collapses 3+ blank lines into 1.
 */
function normalizeMarkdown(md: string): string {
  if (!md) return md;
  const lines = md.split("\n");
  const out: string[] = [];
  // GFM table separator: |---|---| or | --- | :---: |
  const isSeparator = (s: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$/.test(s);
  const isTableRow = (s: string) => /^\s*\|.*\|\s*$/.test(s) || /^\s*\|.*\|/.test(s);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const prev = out[out.length - 1];
    // If this line starts a table (row + next is separator) and the previous
    // output line is non-empty & not blank, insert a blank line first.
    if (
      isTableRow(line) &&
      i + 1 < lines.length &&
      isSeparator(lines[i + 1]) &&
      prev !== undefined &&
      prev.trim() !== ""
    ) {
      out.push("");
    }
    out.push(line);
  }

  // Collapse 3+ consecutive blank lines into 1.
  const collapsed: string[] = [];
  let blankRun = 0;
  for (const l of out) {
    if (l.trim() === "") {
      blankRun += 1;
      if (blankRun <= 1) collapsed.push(l);
    } else {
      blankRun = 0;
      collapsed.push(l);
    }
  }
  return collapsed.join("\n");
}

export function AlphaForge() {
  const [stockInput, setStockInput] = useState("");
  const [market, setMarket] = useState("A-shares");
  const [reports, setReports] = useState<AlphaForgeReportItem[]>([]);
  const [reportsLoading, setReportsLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState<AlphaForgeReportDetail | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"new" | "history">("new");

  const [running, setRunning] = useState(false);
  const [runInfo, setRunInfo] = useState<AlphaForgeRunDetail | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const list = await api.listAlphaForgeReports();
      setReports(list);
    } catch {
      // The report list is nice-to-have for the workspace shell.
    } finally {
      setReportsLoading(false);
    }
  }, []);

  useEffect(() => { loadReports(); }, [loadReports]);

  const startPolling = useCallback((runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const detail = await api.getAlphaForgeRun(runId);
        setRunInfo(detail);
        if (terminalStatus(detail.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
          setRunning(false);
          if (detail.status === "completed") {
            toast.success("AlphaForge 分析完成");
            loadReports();
          } else {
            setRunError(`运行${statusLabel(detail.status)}`);
          }
        }
      } catch {
        // Polling errors are transient while the backend is busy or restarting.
      }
    }, 3000);
  }, [loadReports]);

  useEffect(() => {
    (async () => {
      try {
        const runs = await api.listAlphaForgeRuns();
        // Only resume a run that is (a) non-terminal AND (b) created within
        // the last 30 minutes. Stale/older "running" entries are almost always
        // zombie states (cancelled on disk but the list endpoint lagged, or a
        // crashed process) — resuming them would re-poll forever. The 30-min
        // window covers the longest realistic AlphaForge run.
        const STALE_MS = 30 * 60 * 1000;
        const now = Date.now();
        const inProgress = runs.find((run) => {
          if (terminalStatus(run.status)) return false;
          const createdMs = run.created_at ? Date.parse(run.created_at) : 0;
          if (!createdMs) return false; // can't verify freshness → skip
          return now - createdMs < STALE_MS;
        });
        if (inProgress) {
          setRunning(true);
          setActiveTab("new");
          const detail = await api.getAlphaForgeRun(inProgress.run_id);
          // Double-check the detailed run is still non-terminal (the list
          // snapshot can lag; the detail endpoint reads live task files).
          if (terminalStatus(detail.status)) {
            setRunning(false);
            return;
          }
          setRunInfo(detail);
          startPolling(inProgress.run_id);
          toast.info(`已恢复进行中的分析：${inProgress.target}`);
        }
      } catch {
        // Older backend builds may not expose the run list endpoint.
      }
    })();
    // Intentionally runs once on mount; startPolling is stable enough for this recovery path.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const viewReport = useCallback(async (reportId: string) => {
    setReportLoading(true);
    setActiveTab("history");
    try {
      const detail = await api.getAlphaForgeReport(reportId);
      setSelectedReport(detail);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载报告失败");
    } finally {
      setReportLoading(false);
    }
  }, []);

  const downloadReport = useCallback(async (reportId: string, format: "md" | "pdf") => {
    try {
      const { blob, filename } = await api.downloadAlphaForgeReport(reportId, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "下载报告失败");
    }
  }, []);

  const startRun = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    const target = stockInput.trim();
    if (!target || running) return;

    setRunning(true);
    setRunError(null);
    setRunInfo(null);
    setSelectedReport(null);
    setActiveTab("new");

    try {
      const run = await api.createAlphaForgeRun(target, market);
      setRunInfo({
        ...run,
        preset_name: "alpha_forge",
        completed_at: null,
        final_report: null,
        total_input_tokens: 0,
        total_output_tokens: 0,
        tasks: [],
      });
      startPolling(run.run_id);
    } catch (error) {
      setRunning(false);
      const message = error instanceof Error ? error.message : "启动分析失败";
      setRunError(message);
      toast.error(message);
    }
  }, [market, running, startPolling, stockInput]);

  const cancelRun = useCallback(async () => {
    if (!runInfo) return;
    try {
      await api.cancelAlphaForgeRun(runInfo.run_id);
      if (pollRef.current) clearInterval(pollRef.current);
      setRunning(false);
      toast.info("已取消分析");
    } catch {
      toast.error("取消失败");
    }
  }, [runInfo]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const taskProgress = useMemo(() => {
    if (!runInfo?.tasks) return null;
    return {
      total: runInfo.tasks.length,
      done: runInfo.tasks.filter(isTaskDone).length,
      running: runInfo.tasks.filter((task) => taskDisplayStatus(task) === "in_progress").length,
      waiting: runInfo.tasks.filter((task) => taskDisplayStatus(task) === "waiting").length,
      blocked: runInfo.tasks.filter((task) => taskDisplayStatus(task) === "blocked").length,
      failed: runInfo.tasks.filter((task) => taskDisplayStatus(task) === "failed").length,
    };
  }, [runInfo]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="shrink-0 border-b bg-card/60 px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10">
              <Zap className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">AlphaForge</h1>
              <p className="text-xs text-muted-foreground">多 Agent 投研报告系统</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="hidden max-w-xl rounded-md border bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground xl:block">
              用于单标的正式投研；建议从推荐标的、新闻或逻辑链进入，完成后报告归档到历史报告并支持下载。
            </div>
            <button
              onClick={loadReports}
              disabled={reportsLoading}
              className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
              title="刷新报告列表"
            >
              <RefreshCw className={cn("h-4 w-4", reportsLoading && "animate-spin")} />
              刷新
            </button>
          </div>
        </div>
      </header>

      <div className="shrink-0 border-b px-6">
        {([
          { id: "new" as const, icon: Play, label: "新建分析" },
          { id: "history" as const, icon: FileText, label: `历史报告 (${reports.length})` },
        ]).map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); if (tab.id === "history") loadReports(); }}
            className={cn(
              "inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "new" ? (
        <NewAnalysisView
          market={market}
          running={running}
          runError={runError}
          runInfo={runInfo}
          stockInput={stockInput}
          taskProgress={taskProgress}
          onCancelRun={cancelRun}
          onMarketChange={setMarket}
          onStartRun={startRun}
          onStockInputChange={setStockInput}
        />
      ) : (
        <HistoryView
          reports={reports}
          reportsLoading={reportsLoading}
          reportLoading={reportLoading}
          selectedReport={selectedReport}
          onDownloadReport={downloadReport}
          onViewReport={viewReport}
        />
      )}
    </div>
  );
}

function NewAnalysisView({
  market,
  running,
  runError,
  runInfo,
  stockInput,
  taskProgress,
  onCancelRun,
  onMarketChange,
  onStartRun,
  onStockInputChange,
}: {
  market: string;
  running: boolean;
  runError: string | null;
  runInfo: AlphaForgeRunDetail | null;
  stockInput: string;
  taskProgress: { total: number; done: number; running: number; waiting: number; blocked: number; failed: number } | null;
  onCancelRun: () => void;
  onMarketChange: (value: string) => void;
  onStartRun: (event: FormEvent) => void;
  onStockInputChange: (value: string) => void;
}) {
  return (
    <main className="flex-1 overflow-auto">
      <div className="grid min-h-full gap-6 p-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="space-y-4">
          <Panel title="任务配置" desc="选择标的和市场，启动一条可追踪的投研流水线。">
            <form onSubmit={onStartRun} className="space-y-4">
              <label className="grid gap-2">
                <span className="text-sm font-medium">股票/资产代码</span>
                <input
                  value={stockInput}
                  onChange={(event) => onStockInputChange(event.target.value)}
                  placeholder="例如：300253.SZ"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  disabled={running}
                />
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-medium">市场</span>
                <select
                  value={market}
                  onChange={(event) => onMarketChange(event.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  disabled={running}
                >
                  <option value="A-shares">A 股</option>
                  <option value="Hong Kong">港股</option>
                  <option value="US">美股</option>
                  <option value="crypto">加密货币</option>
                </select>
              </label>

              <button
                type="submit"
                disabled={!stockInput.trim() || running}
                className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {running ? "分析中" : "开始分析"}
              </button>
            </form>
          </Panel>

          {(running || runInfo || runError) && (
            <Panel title="运行状态" desc={runInfo ? `${runInfo.run_id} · ${MARKET_LABELS[market] || market}` : undefined}>
              <RunStatusCard
                running={running}
                runError={runError}
                runInfo={runInfo}
                taskProgress={taskProgress}
                onCancelRun={onCancelRun}
              />
            </Panel>
          )}
        </section>

        <section className="min-w-0 space-y-4">
          <Panel
            title="Agent 流水线"
            desc="按依赖关系展示 19 个 Agent 的执行顺序和等待原因。"
          >
            <AgentPipeline runInfo={runInfo} />
          </Panel>

          <div className="grid gap-4">
            <Panel title="实时产出" desc="显示当前执行和最近完成的 Agent。">
              <LiveOutput runInfo={runInfo} />
            </Panel>
          </div>
        </section>
      </div>
    </main>
  );
}

function RunStatusCard({
  running,
  runError,
  runInfo,
  taskProgress,
  onCancelRun,
}: {
  running: boolean;
  runError: string | null;
  runInfo: AlphaForgeRunDetail | null;
  taskProgress: { total: number; done: number; running: number; waiting: number; blocked: number; failed: number } | null;
  onCancelRun: () => void;
}) {
  const status = runInfo?.status;
  const progressPct = taskProgress?.total ? Math.round((taskProgress.done / taskProgress.total) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{statusLabel(status || (running ? "in_progress" : null))}</span>
        {running ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            正在运行
          </span>
        ) : status === "completed" ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
            <CheckCircle2 className="h-3.5 w-3.5" />
            已完成
          </span>
        ) : null}
      </div>

      {taskProgress && (
        <>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{taskProgress.done}/{taskProgress.total} 个 Agent 完成</span>
            <span>{progressPct}%</span>
          </div>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            {taskProgress.running > 0 && <StatusPill tone="primary">执行中 {taskProgress.running}</StatusPill>}
            {taskProgress.waiting > 0 && <StatusPill tone="muted">等待上游 {taskProgress.waiting}</StatusPill>}
            {taskProgress.blocked > 0 && <StatusPill tone="danger">已阻塞 {taskProgress.blocked}</StatusPill>}
            {taskProgress.failed > 0 && <StatusPill tone="danger">失败 {taskProgress.failed}</StatusPill>}
          </div>
        </>
      )}

      {runInfo?.tasks && runInfo.tasks.length > 0 && (
        <div className="max-h-56 space-y-1 overflow-auto">
          {runInfo.tasks.map((task) => {
            const displayStatus = taskDisplayStatus(task);
            const Icon = TASK_STATUS_ICONS[displayStatus] || Clock;
            return (
              <div key={task.id} className="grid grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-2 rounded-md border bg-muted/20 px-2 py-1.5 text-xs">
                <Icon className={cn(
                  "h-3.5 w-3.5",
                  displayStatus === "in_progress" && "animate-spin text-primary",
                  displayStatus === "completed" && "text-success",
                  displayStatus === "failed" && "text-danger",
                  displayStatus === "blocked" && "text-danger",
                  displayStatus === "waiting" && "text-muted-foreground",
                )} />
                <span className="truncate">{AGENT_LABELS[task.agent_id] || task.agent_id}</span>
                <span className={cn(
                  "text-muted-foreground",
                  displayStatus === "blocked" && "text-danger",
                  displayStatus === "failed" && "text-danger",
                )}>
                  {taskDisplayLabel(task)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {running && (
        <button
          onClick={onCancelRun}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-danger/40 px-3 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/5"
        >
          <XCircle className="h-4 w-4" />
          取消分析
        </button>
      )}

      {runError && (
        <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          {runError}
        </div>
      )}
    </div>
  );
}

type AgentFlowNodeData = {
  agentId: string;
  label: string;
  stage: string;
  status: string;
  statusLabel: string;
  error?: string | null;
};

type AgentFlowNode = Node<AgentFlowNodeData, "agent">;

const FLOW_NODE_TYPES = { agent: AgentFlowNodeCard };

const FLOW_LAYOUT: Array<{ id: string; x: number; y: number; stage: string }> = [
  { id: "data_collector", x: 0, y: 260, stage: "数据采集" },
  { id: "technical_analyst", x: 300, y: 20, stage: "并行研究" },
  { id: "fundamental_analyst", x: 300, y: 120, stage: "并行研究" },
  { id: "news_analyst", x: 300, y: 220, stage: "并行研究" },
  { id: "sentiment_analyst", x: 300, y: 320, stage: "并行研究" },
  { id: "policy_analyst", x: 300, y: 420, stage: "并行研究" },
  { id: "capital_flow_analyst", x: 300, y: 520, stage: "并行研究" },
  { id: "lockup_analyst", x: 300, y: 620, stage: "并行研究" },
  { id: "global_market_analyst", x: 300, y: 720, stage: "并行研究" },
  { id: "quality_gate", x: 650, y: 360, stage: "质量门控" },
  { id: "bull_case", x: 950, y: 240, stage: "多空辩论" },
  { id: "bear_case", x: 950, y: 480, stage: "多空辩论" },
  { id: "bull_rebuttal", x: 1240, y: 220, stage: "第二轮反驳" },
  { id: "bear_rebuttal", x: 1240, y: 500, stage: "第二轮反驳" },
  { id: "neutral_synthesis", x: 1520, y: 360, stage: "中立综合" },
  { id: "trader", x: 1840, y: 360, stage: "交易决策" },
  { id: "risk_officer", x: 2130, y: 360, stage: "风控评估" },
  { id: "portfolio_manager", x: 2420, y: 360, stage: "最终裁决" },
  { id: "report_writer", x: 2710, y: 360, stage: "报告生成" },
];

const FLOW_EDGES: Array<[string, string]> = [
  ["data_collector", "technical_analyst"],
  ["data_collector", "fundamental_analyst"],
  ["data_collector", "news_analyst"],
  ["data_collector", "sentiment_analyst"],
  ["data_collector", "policy_analyst"],
  ["data_collector", "capital_flow_analyst"],
  ["data_collector", "lockup_analyst"],
  ["data_collector", "global_market_analyst"],
  ["technical_analyst", "quality_gate"],
  ["fundamental_analyst", "quality_gate"],
  ["news_analyst", "quality_gate"],
  ["sentiment_analyst", "quality_gate"],
  ["policy_analyst", "quality_gate"],
  ["capital_flow_analyst", "quality_gate"],
  ["lockup_analyst", "quality_gate"],
  ["global_market_analyst", "quality_gate"],
  ["quality_gate", "bull_case"],
  ["quality_gate", "bear_case"],
  ["bull_case", "bull_rebuttal"],
  ["bear_case", "bear_rebuttal"],
  ["bull_rebuttal", "neutral_synthesis"],
  ["bear_rebuttal", "neutral_synthesis"],
  ["neutral_synthesis", "trader"],
  ["trader", "risk_officer"],
  ["risk_officer", "portfolio_manager"],
  ["portfolio_manager", "report_writer"],
];

function AgentPipeline({ runInfo }: { runInfo: AlphaForgeRunDetail | null }) {
  const tasksByAgent = useMemo(() => new Map((runInfo?.tasks || []).map((task) => [task.agent_id, task])), [runInfo]);

  const nodes = useMemo<AgentFlowNode[]>(() => FLOW_LAYOUT.map((item) => {
    const task = tasksByAgent.get(item.id);
    const status = task ? taskDisplayStatus(task) : "pending";
    return {
      id: item.id,
      type: "agent",
      position: { x: item.x, y: item.y },
      data: {
        agentId: item.id,
        label: AGENT_LABELS[item.id] || item.id,
        stage: item.stage,
        status,
        statusLabel: task ? taskDisplayLabel(task) : "未开始",
        error: task?.error,
      },
    };
  }), [tasksByAgent]);

  const edges = useMemo<Edge[]>(() => FLOW_EDGES.map(([source, target]) => ({
    id: `${source}->${target}`,
    source,
    target,
    type: "smoothstep",
    animated: taskDisplayStatus(tasksByAgent.get(source) ?? { id: source, agent_id: source, status: "pending" }) === "in_progress",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 1.6 },
  })), [tasksByAgent]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5 text-[11px]">
        <StatusPill tone="primary">执行中</StatusPill>
        <StatusPill tone="muted">等待上游</StatusPill>
        <StatusPill tone="success">已完成</StatusPill>
        <StatusPill tone="danger">异常</StatusPill>
      </div>
      <div className="h-[280px] overflow-hidden rounded-md border bg-muted/10">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={FLOW_NODE_TYPES}
          defaultViewport={{ x: 32, y: 80, zoom: 0.85 }}
          minZoom={0.2}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background gap={24} size={1} color="hsl(var(--border))" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeStrokeWidth={3} />
        </ReactFlow>
      </div>
    </div>
  );
}

function AgentFlowNodeCard({ data }: NodeProps<AgentFlowNode>) {
  const Icon = TASK_STATUS_ICONS[data.status] || Clock;
  return (
    <div
      title={data.error || data.statusLabel}
      className={cn(
        "min-h-[76px] w-[210px] rounded-md border bg-background px-3 py-2 text-xs shadow-sm",
        data.status === "in_progress" && "border-primary/50 bg-primary/5 shadow-primary/10",
        data.status === "completed" && "border-success/40 bg-success/5",
        (data.status === "failed" || data.status === "blocked") && "border-danger/40 bg-danger/5",
        data.status === "waiting" && "border-dashed bg-muted/30",
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-border !bg-background" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-border !bg-background" />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{data.label}</span>
        <Icon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            data.status === "in_progress" && "animate-spin text-primary",
            data.status === "completed" && "text-success",
            (data.status === "failed" || data.status === "blocked") && "text-danger",
            (data.status === "waiting" || data.status === "pending") && "text-muted-foreground",
          )}
        />
      </div>
      <p className="mt-1 truncate text-[10px] text-muted-foreground">{data.stage}</p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[10px] text-muted-foreground">{data.agentId}</span>
        <span
          className={cn(
            "shrink-0 text-[10px]",
            data.status === "in_progress" && "text-primary",
            data.status === "completed" && "text-success",
            (data.status === "failed" || data.status === "blocked") && "text-danger",
            (data.status === "waiting" || data.status === "pending") && "text-muted-foreground",
          )}
        >
          {data.statusLabel}
        </span>
      </div>
      {data.error && <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-danger">{data.error}</p>}
    </div>
  );
}

function LiveOutput({ runInfo }: { runInfo: AlphaForgeRunDetail | null }) {
  const tasks = runInfo?.tasks ?? [];
  const active = tasks.find((task) => taskDisplayStatus(task) === "in_progress");
  const completed = tasks.filter(isTaskDone);
  const latestCompleted = completed[completed.length - 1];

  if (!runInfo) {
    return (
      <div className="min-h-[150px] rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">
        启动分析后，这里会显示当前执行中的 Agent 和最近完成项。
      </div>
    );
  }

  if (runInfo.status === "completed") {
    return (
      <div className="flex min-h-[150px] items-start gap-3 rounded-md border border-success/30 bg-success/5 p-3 text-sm">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
        <div>
          <div className="font-medium text-success">分析已完成</div>
          <p className="mt-1 text-xs text-muted-foreground">报告已保存到历史报告，可查看 Markdown 或下载 PDF。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[150px] space-y-3 text-sm">
      <LiveOutputRow
        label="当前执行"
        value={active ? AGENT_LABELS[active.agent_id] || active.agent_id : "等待调度"}
        desc={active ? "正在生成该阶段的分析产出。" : "等待上游 Agent 完成后进入下一层。"}
        tone={active ? "primary" : "muted"}
      />
      <LiveOutputRow
        label="最近完成"
        value={latestCompleted ? AGENT_LABELS[latestCompleted.agent_id] || latestCompleted.agent_id : "暂无"}
        desc={latestCompleted ? "该 Agent 的结果会进入后续上下文。" : "data_collector 完成后会先出现共享事实表。"}
        tone={latestCompleted ? "success" : "muted"}
      />
      <div className="rounded-md border bg-muted/20 p-3">
        <p className="text-xs font-medium">报告最终包含</p>
        <div className="mt-2 space-y-1 text-xs text-muted-foreground">
          {REPORT_SECTIONS.map((section) => (
            <div key={section} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/60" />
              {section}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function LiveOutputRow({
  label,
  value,
  desc,
  tone,
}: {
  label: string;
  value: string;
  desc: string;
  tone: "primary" | "success" | "muted";
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{label}</p>
        <StatusPill tone={tone}>{value}</StatusPill>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{desc}</p>
    </div>
  );
}

function StatusPill({ children, tone }: { children: ReactNode; tone: "primary" | "muted" | "danger" | "success" }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 font-medium",
        tone === "primary" && "bg-primary/10 text-primary",
        tone === "muted" && "bg-muted text-muted-foreground",
        tone === "danger" && "bg-danger/10 text-danger",
        tone === "success" && "bg-success/10 text-success",
      )}
    >
      {children}
    </span>
  );
}

function HistoryView({
  reports,
  reportsLoading,
  reportLoading,
  selectedReport,
  onDownloadReport,
  onViewReport,
}: {
  reports: AlphaForgeReportItem[];
  reportsLoading: boolean;
  reportLoading: boolean;
  selectedReport: AlphaForgeReportDetail | null;
  onDownloadReport: (reportId: string, format: "md" | "pdf") => void;
  onViewReport: (reportId: string) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <aside className="w-80 shrink-0 overflow-auto border-r bg-card/50 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">历史报告</h2>
          {reportsLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
        {reportsLoading ? (
          <div className="flex justify-center py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : reports.length === 0 ? (
          <p className="rounded-md border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
            暂无报告，请先新建分析。
          </p>
        ) : (
          <div className="space-y-1">
            {reports.map((report) => (
              <button
                key={report.report_id}
                onClick={() => onViewReport(report.report_id)}
                className={cn(
                  "w-full rounded-md border border-transparent px-3 py-2.5 text-left transition-colors hover:bg-muted",
                  selectedReport?.report_id === report.report_id && "border-primary/30 bg-primary/10",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{report.stock_name || report.target}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    {qualityBadge(report)}
                    {signalBadge(report.signal)}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="font-mono">{report.target}</span>
                  <span>{MARKET_LABELS[report.market] || report.market}</span>
                  <span>{shortDate(report.analysis_date || report.created_at)}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-auto">
        {reportLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            正在加载报告…
          </div>
        ) : selectedReport ? (
          <ReportViewer
            report={selectedReport}
            onDownload={(format) => onDownloadReport(selectedReport.report_id, format)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
            <BarChart3 className="h-12 w-12 opacity-30" />
            <p className="text-sm">选择一份报告查看</p>
            <p className="text-xs opacity-70">从左侧列表选择已有报告，或回到新建分析生成新的报告。</p>
          </div>
        )}
      </main>
    </div>
  );
}

function ReportViewer({
  report,
  onDownload,
}: {
  report: AlphaForgeReportDetail;
  onDownload: (format: "md" | "pdf") => void | Promise<void>;
}) {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex flex-col gap-4 border-b pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold">{report.stock_name || report.target}</h2>
            {signalBadge(report.signal)}
            {qualityBadge(report)}
            {report.rating && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {report.rating}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span className="font-mono">{report.target}</span>
            <span>{MARKET_LABELS[report.market] || report.market}</span>
            <span>分析日期：{shortDate(report.analysis_date || report.created_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onDownload("md")}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
          >
            <FileDown className="h-3.5 w-3.5" />
            下载 Markdown
          </button>
          <button
            onClick={() => onDownload("pdf")}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Download className="h-3.5 w-3.5" />
            下载 PDF
          </button>
        </div>
      </div>

      {report.report_quality && report.report_quality !== "ok" && (
        <div className={cn(
          "mb-4 rounded-md border px-4 py-3 text-sm",
          report.report_quality === "unreliable"
            ? "border-danger/30 bg-danger/5 text-danger"
            : "border-warning/30 bg-warning/5 text-warning",
        )}>
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">
                {report.report_quality === "unreliable" ? "数据质量不可信，不建议直接作为投研结论使用" : "数据质量存疑，阅读时需核对关键数据"}
              </p>
              {report.quality_warnings && report.quality_warnings.length > 0 && (
                <p className="mt-1 text-xs leading-5 opacity-90">{report.quality_warnings.join("；")}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {report.decision_warnings && report.decision_warnings.length > 0 && (
        <div className="mb-4 rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">交易决策硬校验存在风险</p>
              <ul className="mt-1 space-y-1 text-xs leading-5 opacity-90">
                {report.decision_warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_240px]">
        <article className="prose prose-sm max-w-none dark:prose-invert prose-headings:border-b prose-headings:pb-2 prose-headings:mt-8 prose-headings:mb-4 prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-table:text-xs prose-th:bg-muted/50 prose-th:font-semibold prose-td:px-3 prose-td:py-2 prose-blockquote:border-l-primary prose-blockquote:bg-muted/20 prose-blockquote:px-4 prose-blockquote:py-1 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-li:text-sm prose-p:text-sm [&_pre]:bg-muted/40 [&_pre]:p-4 [&_pre]:rounded-lg [&_pre]:overflow-x-auto [&_pre]:text-[12px] [&_pre]:leading-[1.5] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:font-mono [&_pre_code]:whitespace-pre [&_pre_code]:text-foreground/90 [&_pre_code]:tracking-tight [&_code]:font-mono">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {normalizeMarkdown(report.content_md)}
          </ReactMarkdown>
        </article>

        <aside className="space-y-3">
          <div className="rounded-md border bg-card p-3">
            <h3 className="text-sm font-semibold">报告目录</h3>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              {REPORT_SECTIONS.map((section) => (
                <div key={section} className="rounded bg-muted/30 px-2 py-1">{section}</div>
              ))}
            </div>
          </div>
          <div className="rounded-md border border-warning/30 bg-warning/5 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <div className="text-xs text-muted-foreground">
                <p className="font-semibold text-warning">免责声明</p>
                <p className="mt-1 leading-relaxed">
                  本报告由 AI 多 Agent 系统自动生成，仅供学习研究与技术演示，不构成任何投资建议。投资决策请咨询持牌专业机构。
                </p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Panel({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-md border bg-card">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {desc && <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
