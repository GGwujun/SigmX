import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertTriangle, CheckCircle2, Clock, Download, FileDown, Loader2,
  Play, XCircle, Coins, Zap,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import {
  api, type FundReportDetail, type FundReportItem, type FundRunDetail,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const FUND_TYPES = [
  { value: "ETF", label: "ETF" },
  { value: "LOF", label: "LOF" },
  { value: "QDII", label: "QDII" },
  { value: "分级", label: "分级" },
  { value: "封基", label: "封基" },
];

const AGENT_LABELS: Record<string, string> = {
  data_collector: "数据采集",
  premium_analyst: "折溢价分析",
  liquidity_analyst: "流动性评估",
  holdings_analyst: "成分股分析",
  cost_analyst: "成本核算",
  risk_officer: "风控评估",
  report_writer: "报告总撰",
};

const STATUS_ICON: Record<string, typeof Play> = {
  pending: Clock, in_progress: Loader2, completed: CheckCircle2,
  failed: XCircle, blocked: AlertTriangle, cancelled: XCircle,
};

function terminalStatus(s?: string | null) {
  return ["completed", "failed", "cancelled"].includes(s || "");
}

/* ─── Report viewer ─── */
function ReportViewer({
  report, onDownload,
}: {
  report: FundReportDetail;
  onDownload: (format: "md" | "pdf") => void;
}) {
  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-xl font-bold">{report.fund_name || report.fund_code}</h2>
            {report.premium_rate && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-mono">{report.premium_rate}</span>
            )}
            {report.rating && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">{report.rating}</span>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {report.fund_code} · {report.fund_type} · {report.analysis_date || report.created_at?.slice(0, 10)}
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => onDownload("md")} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium hover:bg-muted transition-colors">
            <FileDown className="h-3.5 w-3.5" /> MD
          </button>
          <button onClick={() => onDownload("pdf")} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition">
            <Download className="h-3.5 w-3.5" /> PDF
          </button>
        </div>
      </div>
      <article className="prose prose-sm dark:prose-invert max-w-none prose-headings:border-b prose-headings:pb-2 prose-headings:mt-8 prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-table:text-xs prose-th:bg-muted/50 prose-th:font-semibold prose-td:px-3 prose-td:py-2 prose-blockquote:border-l-primary prose-blockquote:bg-muted/20 prose-blockquote:px-4 prose-blockquote:py-1 prose-li:text-sm prose-p:text-sm [&_pre]:bg-muted/40 [&_pre]:p-4 [&_pre]:rounded-lg [&_pre]:overflow-x-auto [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:font-mono [&_pre_code]:whitespace-pre">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {report.content_md}
        </ReactMarkdown>
      </article>
    </div>
  );
}

/* ─── Main component ─── */
export function FundArbitrage() {
  const [searchParams] = useSearchParams();
  const urlCode = searchParams.get("code") || "";
  const urlType = searchParams.get("type") || "ETF";

  const [analyzeCode, setAnalyzeCode] = useState(urlCode);
  const [analyzeType, setAnalyzeType] = useState(urlType);
  const [running, setRunning] = useState(false);
  const [runInfo, setRunInfo] = useState<FundRunDetail | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [reports, setReports] = useState<FundReportItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<FundReportDetail | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const loadReports = useCallback(async () => {
    try { setReports(await api.listFundReports()); } catch { /* silent */ }
  }, []);

  useEffect(() => { loadReports(); }, [loadReports]);

  // 当 URL 参数变化时（从机会清单跳来），更新输入框
  useEffect(() => {
    if (urlCode) { setAnalyzeCode(urlCode); setAnalyzeType(urlType); }
  }, [urlCode, urlType]);

  /* polling */
  const startPolling = useCallback((runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const d = await api.getFundRun(runId);
        setRunInfo(d);
        if (terminalStatus(d.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
          setRunning(false);
          if (d.status === "completed") { toast.success("套利分析完成"); loadReports(); }
          else setRunError(`运行${d.status}`);
        }
      } catch { /* transient */ }
    }, 3000);
  }, [loadReports]);

  /* resume in-progress on mount */
  useEffect(() => {
    (async () => {
      try {
        const runs = await api.listFundRuns();
        const live = runs.find(r => !terminalStatus(r.status));
        if (live && live.created_at && Date.now() - Date.parse(live.created_at) < 30 * 60 * 1000) {
          setRunning(true);
          setAnalyzeCode(live.fund_code); setAnalyzeType(live.fund_type);
          const d = await api.getFundRun(live.run_id);
          if (!terminalStatus(d.status)) { setRunInfo(d); startPolling(live.run_id); }
          else setRunning(false);
        }
      } catch { /* silent */ }
    })();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startAnalyze = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    const code = analyzeCode.trim();
    if (!code || running) return;
    setRunning(true); setRunError(null); setRunInfo(null); setSelectedReport(null);
    try {
      const run = await api.analyzeFund(code, analyzeType);
      setRunInfo({ ...run, preset_name: "fund_arbitrage", completed_at: null, final_report: null, tasks: [] });
      startPolling(run.run_id);
    } catch (err) {
      setRunning(false);
      const msg = err instanceof Error ? err.message : "启动分析失败";
      setRunError(msg); toast.error(msg);
    }
  }, [analyzeCode, analyzeType, running, startPolling]);

  const cancelRun = useCallback(async () => {
    if (!runInfo) return;
    try {
      await api.cancelFundRun(runInfo.run_id);
      if (pollRef.current) clearInterval(pollRef.current);
      setRunning(false); toast.info("已取消");
    } catch { toast.error("取消失败"); }
  }, [runInfo]);

  const viewReport = useCallback(async (reportId: string) => {
    setReportLoading(true);
    try { setSelectedReport(await api.getFundReport(reportId)); }
    catch (e) { toast.error(e instanceof Error ? e.message : "加载失败"); }
    finally { setReportLoading(false); }
  }, []);

  const downloadReport = useCallback((reportId: string, format: "md" | "pdf") => {
    window.open(api.getFundReportDownloadUrl(reportId, format), "_blank");
  }, []);

  const taskProgress = runInfo?.tasks
    ? { done: runInfo.tasks.filter(t => t.status === "completed").length, total: runInfo.tasks.length }
    : null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* header */}
      <header className="border-b px-6 py-4 flex items-center gap-3 shrink-0">
        <div className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center">
          <Coins className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-lg font-bold">套利分析</h1>
          <p className="text-xs text-muted-foreground">输入基金代码，生成 6-Agent 深度套利报告</p>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* left sidebar: analyze form + history */}
        <aside className="border-r bg-card/50 w-72 shrink-0 overflow-auto">
          <div className="p-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">生成深度报告</h3>
            <form onSubmit={startAnalyze} className="space-y-3">
              <input value={analyzeCode} onChange={e => setAnalyzeCode(e.target.value)}
                placeholder="基金代码 如 161725"
                disabled={running}
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              <select value={analyzeType} onChange={e => setAnalyzeType(e.target.value)} disabled={running}
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
                {FUND_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <button type="submit" disabled={!analyzeCode.trim() || running}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-40">
                {running ? <><Loader2 className="h-4 w-4 animate-spin" /> 分析中…</> : <><Play className="h-4 w-4" /> 开始分析</>}
              </button>
            </form>

            {(running || runInfo) && (
              <div className="mt-4 p-3 rounded-xl border bg-background space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold">运行状态</span>
                  {running ? <span className="text-xs text-primary flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" />进行中</span>
                    : runInfo?.status === "completed" ? <span className="text-xs text-success flex items-center gap-1"><CheckCircle2 className="h-3 w-3" />完成</span>
                    : <span className="text-xs text-danger flex items-center gap-1"><XCircle className="h-3 w-3" />{runInfo?.status}</span>}
                </div>
                {taskProgress && (
                  <>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${taskProgress.total ? (taskProgress.done / taskProgress.total) * 100 : 0}%` }} />
                    </div>
                    <p className="text-[11px] text-muted-foreground">{taskProgress.done}/{taskProgress.total} Agent 完成</p>
                    {(runInfo?.tasks ?? []).map(t => {
                      const Icon = STATUS_ICON[t.status] || Clock;
                      return (
                        <div key={t.id} className="flex items-center gap-2 text-[11px]">
                          <Icon className={cn("h-3 w-3 shrink-0", t.status === "in_progress" && "animate-spin text-primary", t.status === "completed" && "text-success", t.status === "failed" && "text-danger")} />
                          <span className="text-muted-foreground truncate">{AGENT_LABELS[t.agent_id] || t.agent_id}</span>
                        </div>
                      );
                    })}
                  </>
                )}
                {running && <button onClick={cancelRun} className="w-full mt-1 px-3 py-1.5 rounded-lg border border-danger/40 text-xs text-danger hover:bg-danger/5">取消</button>}
                {runError && <p className="text-[11px] text-danger">{runError}</p>}
              </div>
            )}
            <hr className="my-4" />
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              6 个 Agent（数据采集 → 折溢价/流动性/成分股/成本并行 → 风控 → 报告总撰），约 10-15 分钟。
            </p>
          </div>

          {/* history */}
          <div className="p-4 border-t">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">历史报告</h3>
            {reports.length === 0 ? <p className="text-xs text-muted-foreground py-4 text-center">暂无报告</p> : (
              <div className="space-y-1">
                {reports.map(r => (
                  <button key={r.report_id} onClick={() => viewReport(r.report_id)}
                    className={cn("w-full text-left px-3 py-2.5 rounded-lg transition-colors hover:bg-muted",
                      selectedReport?.report_id === r.report_id && "bg-primary/10 border border-primary/20")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium truncate">{r.fund_name || r.fund_code}</span>
                      {r.premium_rate && <span className="text-[10px] font-mono">{r.premium_rate}</span>}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">{r.fund_code} · {r.analysis_date || r.created_at?.slice(0, 10)}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* main */}
        <main className="flex-1 overflow-auto">
          {reportLoading ? (
            <div className="flex items-center justify-center h-full"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : selectedReport ? (
            <ReportViewer report={selectedReport} onDownload={fmt => downloadReport(selectedReport.report_id, fmt)} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
              <Zap className="h-12 w-12 opacity-30" />
              <p className="text-sm">输入基金代码生成深度套利报告</p>
              <p className="text-xs opacity-60">或从「套利机会」清单点选基金跳转至此</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
