import { useEffect, useState, useCallback, useRef, type FormEvent } from "react";
import {
  BarChart3, Download, FileText, Loader2, Play, AlertTriangle,
  CheckCircle2, XCircle, Clock, FileDown, Zap, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type AlphaForgeReportItem, type AlphaForgeReportDetail, type AlphaForgeRunDetail } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";

/* ─── Constants ─── */
const SIGNAL_COLORS: Record<string, string> = {
  BUY: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10",
  SELL: "text-red-600 dark:text-red-400 bg-red-500/10",
  HOLD: "text-amber-600 dark:text-amber-400 bg-amber-500/10",
  "买入": "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10",
  "卖出": "text-red-600 dark:text-red-400 bg-red-500/10",
  "持有": "text-amber-600 dark:text-amber-400 bg-amber-500/10",
  "减持": "text-red-600 dark:text-red-400 bg-red-500/10",
};

const AGENT_LABELS: Record<string, string> = {
  technical_analyst: "技术分析",
  sentiment_analyst: "情绪分析",
  news_analyst: "新闻舆情",
  fundamental_analyst: "基本面",
  policy_analyst: "政策分析",
  capital_flow_analyst: "游资追踪",
  lockup_analyst: "解禁监控",
  quality_gate: "质量门控",
  bull_case: "多方论证",
  bear_case: "空方论证",
  neutral_synthesis: "中立综合",
  trader: "交易决策",
  risk_officer: "风控评估",
  portfolio_manager: "最终决策",
};

const TASK_STATUS_ICONS: Record<string, typeof Play> = {
  pending: Clock,
  in_progress: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  blocked: AlertTriangle,
  cancelled: XCircle,
};

function signalBadge(signal: string) {
  const color = SIGNAL_COLORS[signal] || "text-muted-foreground bg-muted";
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold", color)}>
      {signal || "—"}
    </span>
  );
}

/* ─── Component ─── */
export function AlphaForge() {
  const [stockInput, setStockInput] = useState("");
  const [market, setMarket] = useState("A-shares");
  const [reports, setReports] = useState<AlphaForgeReportItem[]>([]);
  const [reportsLoading, setReportsLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState<AlphaForgeReportDetail | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"new" | "history">("new");

  // Run state
  const [running, setRunning] = useState(false);
  const [runInfo, setRunInfo] = useState<AlphaForgeRunDetail | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  /* ─── Load report list ─── */
  const loadReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const list = await api.listAlphaForgeReports();
      setReports(list);
    } catch {
      // silent
    } finally {
      setReportsLoading(false);
    }
  }, []);

  useEffect(() => { loadReports(); }, [loadReports]);

  /* ─── View report ─── */
  const viewReport = useCallback(async (reportId: string) => {
    setReportLoading(true);
    setActiveTab("history");
    try {
      const detail = await api.getAlphaForgeReport(reportId);
      setSelectedReport(detail);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载报告失败");
    } finally {
      setReportLoading(false);
    }
  }, []);

  /* ─── Download report ─── */
  const downloadReport = useCallback((reportId: string, format: "md" | "pdf") => {
    const url = api.getAlphaForgeReportDownloadUrl(reportId, format);
    window.open(url, "_blank");
  }, []);

  /* ─── Start run ─── */
  const startRun = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    const target = stockInput.trim();
    if (!target || running) return;

    setRunning(true);
    setRunError(null);
    setRunInfo(null);
    setActiveTab("new");

    try {
      const run = await api.createAlphaForgeRun(target, market);
      setRunInfo({ ...run, preset_name: "alpha_forge", completed_at: null, final_report: null, total_input_tokens: 0, total_output_tokens: 0, tasks: [] });

      // Poll for updates
      pollRef.current = setInterval(async () => {
        try {
          const detail = await api.getAlphaForgeRun(run.run_id);
          setRunInfo(detail);
          if (["completed", "failed", "cancelled"].includes(detail.status)) {
            if (pollRef.current) clearInterval(pollRef.current);
            setRunning(false);
            if (detail.status === "completed") {
              toast.success("AlphaForge 分析完成！");
              loadReports(); // refresh report list
            } else {
              setRunError(`运行 ${detail.status}`);
            }
          }
        } catch {
          // polling error, ignore
        }
      }, 3000);
    } catch (e) {
      setRunning(false);
      setRunError(e instanceof Error ? e.message : "启动分析失败");
      toast.error(e instanceof Error ? e.message : "启动分析失败");
    }
  }, [stockInput, market, running, loadReports]);

  /* ─── Cancel run ─── */
  const cancelRun = useCallback(async () => {
    if (!runInfo) return;
    try {
      await api.cancelSwarmRun(runInfo.run_id);
      if (pollRef.current) clearInterval(pollRef.current);
      setRunning(false);
      toast.info("已取消");
    } catch {
      toast.error("取消失败");
    }
  }, [runInfo]);

  /* ─── Cleanup poll on unmount ─── */
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  /* ─── Compute agent progress ─── */
  const taskProgress = runInfo?.tasks
    ? { total: runInfo.tasks.length, done: runInfo.tasks.filter(t => t.status === "completed").length }
    : null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ── */}
      <header className="border-b px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-violet-500/10 flex items-center justify-center">
            <Zap className="h-4 w-4 text-violet-500" />
          </div>
          <div>
            <h1 className="text-lg font-bold">AlphaForge</h1>
            <p className="text-xs text-muted-foreground">多 Agent 投研报告系统</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadReports}
            disabled={reportsLoading}
            className="p-2 rounded-lg hover:bg-muted transition-colors"
            title="刷新报告列表"
          >
            <RefreshCw className={cn("h-4 w-4", reportsLoading && "animate-spin")} />
          </button>
        </div>
      </header>

      {/* ── Tabs ── */}
      <div className="border-b px-6 flex gap-0 shrink-0">
        {([
          { id: "new" as const, icon: Play, label: "新建分析" },
          { id: "history" as const, icon: FileText, label: `历史报告 (${reports.length})` },
        ]).map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); if (tab.id === "history") loadReports(); }}
            className={cn(
              "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
              activeTab === tab.id
                ? "border-violet-500 text-violet-600 dark:text-violet-400"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Body ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Sidebar (report list) ── */}
        <aside className={cn(
          "border-r bg-card/50 overflow-auto shrink-0 transition-all",
          selectedReport ? "w-64" : "w-72",
        )}>
          {activeTab === "new" && (
            <div className="p-4">
              <form onSubmit={startRun} className="space-y-3">
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  股票代码
                </label>
                <div className="flex gap-2">
                  <input
                    value={stockInput}
                    onChange={e => setStockInput(e.target.value)}
                    placeholder="例: 300253.SZ"
                    className="flex-1 px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                    disabled={running}
                  />
                </div>

                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  市场
                </label>
                <select
                  value={market}
                  onChange={e => setMarket(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                  disabled={running}
                >
                  <option value="A-shares">A 股</option>
                  <option value="Hong Kong">港股</option>
                  <option value="US">美股</option>
                  <option value="crypto">加密货币</option>
                </select>

                <button
                  type="submit"
                  disabled={!stockInput.trim() || running}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-violet-500 text-white text-sm font-semibold hover:bg-violet-600 disabled:opacity-40 transition-all"
                >
                  {running ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> 分析中…</>
                  ) : (
                    <><Play className="h-4 w-4" /> 开始分析</>
                  )}
                </button>
              </form>

              {/* ── Run progress ── */}
              {(running || runInfo) && (
                <div className="mt-4 p-3 rounded-xl border bg-background space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold">运行状态</span>
                    {running ? (
                      <span className="text-xs text-violet-600 font-medium flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" />进行中
                      </span>
                    ) : runInfo?.status === "completed" ? (
                      <span className="text-xs text-emerald-600 font-medium flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" />完成
                      </span>
                    ) : (
                      <span className="text-xs text-red-500 font-medium flex items-center gap-1">
                        <XCircle className="h-3 w-3" />{runInfo?.status}
                      </span>
                    )}
                  </div>

                  {taskProgress && (
                    <>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-violet-500 transition-all duration-500"
                          style={{ width: `${taskProgress.total ? (taskProgress.done / taskProgress.total) * 100 : 0}%` }}
                        />
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {taskProgress.done}/{taskProgress.total} Agent 完成
                      </p>
                    </>
                  )}

                  {runInfo?.tasks && (
                    <div className="space-y-1 max-h-48 overflow-auto">
                      {runInfo.tasks.map(t => {
                        const Icon = TASK_STATUS_ICONS[t.status] || Clock;
                        return (
                          <div key={t.id} className="flex items-center gap-2 text-[11px]">
                            <Icon className={cn(
                              "h-3 w-3 shrink-0",
                              t.status === "in_progress" && "animate-spin text-violet-500",
                              t.status === "completed" && "text-emerald-500",
                              t.status === "failed" && "text-red-500",
                            )} />
                            <span className="text-muted-foreground truncate">
                              {AGENT_LABELS[t.agent_id] || t.agent_id}
                            </span>
                            <span className="text-muted-foreground/60 ml-auto shrink-0">
                              {t.status === "in_progress" ? "执行中" : t.status === "completed" ? "✓" : ""}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {running && (
                    <button
                      onClick={cancelRun}
                      className="w-full mt-1 px-3 py-1.5 rounded-lg border border-destructive/40 text-xs text-destructive hover:bg-destructive/5 transition-colors"
                    >
                      取消
                    </button>
                  )}

                  {runError && (
                    <p className="text-[11px] text-red-500">{runError}</p>
                  )}
                </div>
              )}

              <hr className="my-4" />
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                输入股票代码启动 AlphaForge 多 Agent 投研流水线。7 个专业研究员并行分析 → 质量门控 → 多空辩论 → 交易决策 → 风控审核 → PM 最终裁决。分析完成后自动保存报告。
              </p>
            </div>
          )}

          {activeTab === "history" && (
            <div className="p-4">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                历史报告
              </h3>
              {reportsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : reports.length === 0 ? (
                <p className="text-xs text-muted-foreground py-4 text-center">
                  暂无报告，请先新建分析
                </p>
              ) : (
                <div className="space-y-1">
                  {reports.map(r => (
                    <button
                      key={r.report_id}
                      onClick={() => viewReport(r.report_id)}
                      className={cn(
                        "w-full text-left px-3 py-2.5 rounded-lg transition-colors hover:bg-muted",
                        selectedReport?.report_id === r.report_id && "bg-violet-500/10 border border-violet-500/20",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium truncate">
                          {r.stock_name || r.target}
                        </span>
                        {signalBadge(r.signal)}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground">
                        <span>{r.target}</span>
                        <span>·</span>
                        <span>{r.analysis_date || r.created_at?.slice(0, 10)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>

        {/* ── Main content ── */}
        <main className="flex-1 overflow-auto" ref={listRef}>
          {reportLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : selectedReport ? (
            <ReportViewer
              report={selectedReport}
              onDownload={format => downloadReport(selectedReport.report_id, format)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
              <BarChart3 className="h-12 w-12 opacity-30" />
              <p className="text-sm">选择一份报告查看</p>
              <p className="text-xs opacity-60">从左侧列表选择已有报告，或新建分析</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

/* ─── Report Viewer ─── */
function ReportViewer({
  report,
  onDownload,
}: {
  report: AlphaForgeReportDetail;
  onDownload: (format: "md" | "pdf") => void;
}) {
  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Report header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-xl font-bold">
              {report.stock_name || report.target}
            </h2>
            {signalBadge(report.signal)}
            {report.rating && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                {report.rating}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{report.target}</span>
            <span>·</span>
            <span>{report.market}</span>
            <span>·</span>
            <span>分析日期: {report.analysis_date || report.created_at?.slice(0, 10)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onDownload("md")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium hover:bg-muted transition-colors"
          >
            <FileDown className="h-3.5 w-3.5" />
            MD
          </button>
          <button
            onClick={() => onDownload("pdf")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-500 text-white text-xs font-medium hover:bg-violet-600 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            PDF
          </button>
        </div>
      </div>

      {/* Report content */}
      <div className="prose prose-sm dark:prose-invert max-w-none
        prose-headings:border-b prose-headings:pb-2 prose-headings:mt-8 prose-headings:mb-4
        prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg
        prose-table:text-xs prose-th:bg-muted/50 prose-th:font-semibold
        prose-td:py-2 prose-td:px-3
        prose-blockquote:border-l-violet-400 prose-blockquote:bg-muted/20 prose-blockquote:py-1 prose-blockquote:px-4
        prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded
        prose-li:text-sm prose-p:text-sm
      ">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
          {report.content_md}
        </ReactMarkdown>
      </div>

      {/* Disclaimer */}
      <div className="mt-8 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-xs text-muted-foreground">
            <p className="font-semibold text-amber-600 dark:text-amber-400 mb-1">免责声明</p>
            <p>
              本报告由 AI 多 Agent 系统自动生成，仅供学习研究与技术演示，不构成任何投资建议。
              投资决策请咨询持牌专业机构，使用本报告所产生的任何损失由使用者自行承担。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
