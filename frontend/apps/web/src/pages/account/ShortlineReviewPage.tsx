/**
 * AI 短线复盘页（/account/shortline-review）——线 E 产物的前端暴露。
 *
 * 三块：最新复盘五段原文（含 gate/审计警示）+ 明日验证条件对账状态表
 * （T+1 自动对账，也可手动补对）+ 条件战绩（命中率与基准发生率校正 edge）。
 * 对账状态是机器核对的事实，不是模型自报——徽标颜色按状态渲染。
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, NotebookPen, Play, Scale } from "lucide-react";
import { toast } from "sonner";

import { AccountPage } from "@/components/account/AccountPage";
import { ApiError } from "@/lib/api";
import {
  DIRECTION_LABELS, METRIC_LABELS, getLatestReview, getTrackRecord,
  startReview, verifyConditions, type ShortlineReview, type TrackRecord,
} from "@/lib/shortlineApi";

const SECTION_TITLES: Record<string, string> = {
  sentiment: "情绪",
  capital: "资金",
  theme: "主题",
  ladder: "梯队",
  summary: "汇总",
};

const VERIFICATION_BADGES: Record<string, { label: string; cls: string }> = {
  pending: { label: "待对账", cls: "bg-muted text-muted-foreground" },
  verified: { label: "命中", cls: "bg-emerald-500/10 text-emerald-600" },
  mismatch: { label: "未中", cls: "bg-red-500/10 text-red-600" },
  no_data: { label: "无数据", cls: "bg-amber-500/10 text-amber-600" },
};

function statusBadge(status: string): { label: string; cls: string } {
  return VERIFICATION_BADGES[status]
    ?? { label: status, cls: "bg-muted text-muted-foreground" };
}

function shortDateTime(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function ShortlineReviewPage() {
  const [review, setReview] = useState<ShortlineReview | null>(null);
  const [track, setTrack] = useState<TrackRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [latest, record] = await Promise.all([
        getLatestReview(), getTrackRecord(),
      ]);
      setReview(latest);
      setTrack(record);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载短线复盘失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const onStart = async () => {
    setBusy(true);
    try {
      const row = await startReview();
      toast.success(`复盘已开始生成（${row.trade_date}），稍后刷新查看`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "发起复盘失败");
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async () => {
    setBusy(true);
    try {
      const result = await verifyConditions();
      toast.success(
        `对账完成（${result.condition_date}）：核对 ${result.checked} 条，`
        + `命中 ${result.verified}、未中 ${result.mismatch}、无数据 ${result.no_data}`
        + (result.remaining ? `、剩 ${result.remaining} 条待数据` : ""),
      );
      await reload();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "手动对账失败");
    } finally {
      setBusy(false);
    }
  };

  const sections = review
    ? Object.keys(SECTION_TITLES).filter((k) => review.sections[k])
    : [];

  return (
    <AccountPage>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <NotebookPen className="h-5 w-5 text-primary" /> AI 短线复盘
          </h1>
          <p className="text-xs text-muted-foreground">
            每日五段复盘 + 明日验证条件（T+1 收盘后机器自动对账，战绩按基准发生率校正）
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onStart} disabled={busy}
            className="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50">
            <Play className="h-3.5 w-3.5" /> 生成复盘
          </button>
          <button onClick={onVerify} disabled={busy} title="手动对账（等价于 worker 自动对账）"
            className="flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50">
            <Scale className="h-3.5 w-3.5" /> 手动对账
          </button>
          <button onClick={reload} className="rounded-lg p-2 hover:bg-muted" title="刷新">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center py-10 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载复盘…
        </div>
      ) : !review ? (
        <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
          还没有复盘记录。点「生成复盘」用当日短线快照生成五段复盘（需要数据管道已有当日数据）。
        </p>
      ) : (
        <>
          <section className="rounded-xl border bg-card p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <span className="font-mono text-sm">{review.trade_date}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {review.status === "completed" ? "已生成" : review.status}
                  {review.model ? ` · ${review.model}` : ""}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">
                {shortDateTime(review.finished_at ?? review.created_at)}
              </span>
            </div>
            {review.error && (
              <p className="mt-2 rounded-md bg-red-500/10 px-3 py-1.5 text-xs text-red-600">
                {review.error}
              </p>
            )}
            <div className="mt-3 space-y-3">
              {sections.map((key) => {
                const sec = review.sections[key];
                return (
                  <details key={key} open={key === "summary"} className="rounded-lg border">
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
                      {SECTION_TITLES[key]}
                      {!sec.gate_ok && (
                        <span className="ml-2 rounded bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-600">
                          合规 gate 命中 {sec.gate_hits} 处
                        </span>
                      )}
                      {sec.unknown_citations > 0 && (
                        <span className="ml-2 rounded bg-red-500/10 px-1.5 py-0.5 text-xs text-red-600">
                          未知引用 {sec.unknown_citations} 处
                        </span>
                      )}
                    </summary>
                    <pre className="whitespace-pre-wrap border-t px-3 py-2 font-sans text-sm leading-relaxed text-foreground/90">
                      {sec.text}
                    </pre>
                  </details>
                );
              })}
            </div>
            {review.gaps.length > 0 && (
              <p className="mt-3 text-xs text-muted-foreground">
                数据缺口：{review.gaps.join("；")}
              </p>
            )}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">明日验证条件 · 对账状态</h2>
            {review.conditions.length === 0 ? (
              <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
                本期复盘没有输出验证条件（或解析失败记入 gaps）。
              </p>
            ) : (
              <div className="overflow-hidden rounded-xl border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">指标</th>
                      <th className="px-4 py-2 text-left font-medium">预判</th>
                      <th className="px-4 py-2 text-left font-medium">依据</th>
                      <th className="px-4 py-2 text-left font-medium">T → T+1 实读</th>
                      <th className="px-4 py-2 text-left font-medium">对账</th>
                    </tr>
                  </thead>
                  <tbody>
                    {review.conditions.map((cond, i) => {
                      const v = cond.verification;
                      const badge = statusBadge(v?.status ?? "pending");
                      const values = v && v.status !== "pending"
                        ? `${v.prev_value ?? "—"} → ${v.cur_value ?? "—"}`
                        : "—";
                      return (
                        <tr key={i} className="border-t">
                          <td className="px-4 py-2">{METRIC_LABELS[cond.metric] ?? cond.metric}</td>
                          <td className="px-4 py-2">{DIRECTION_LABELS[cond.direction] ?? cond.direction}</td>
                          <td className="max-w-[18rem] truncate px-4 py-2 text-muted-foreground" title={cond.note}>
                            {cond.note || "—"}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs">{values}</td>
                          <td className="px-4 py-2">
                            <span className={`rounded px-2 py-0.5 text-xs ${badge.cls}`}>{badge.label}</span>
                            {v?.late === 1 && (
                              <span className="ml-1 text-xs text-amber-600" title="条件写入晚于 T+1 09:15，对账但不计战绩">
                                迟写
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">
              条件战绩（近 {track?.window_days ?? 60} 个已决交易日）
            </h2>
            {!track || track.decided === 0 ? (
              <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
                还没有已对账的条件。T+1 收盘后数据管道自动对账，或点「手动对账」。
              </p>
            ) : (
              <div className="overflow-hidden rounded-xl border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">指标</th>
                      <th className="px-4 py-2 text-left font-medium">方向</th>
                      <th className="px-4 py-2 text-right font-medium">已决</th>
                      <th className="px-4 py-2 text-right font-medium">命中</th>
                      <th className="px-4 py-2 text-right font-medium">命中率</th>
                      <th className="px-4 py-2 text-right font-medium">基准发生率</th>
                      <th className="px-4 py-2 text-right font-medium">edge</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(track.by_metric).flatMap(([metric, m]) =>
                      Object.entries(m.by_direction).map(([direction, d]) => (
                        <tr key={`${metric}:${direction}`} className="border-t">
                          <td className="px-4 py-2">{METRIC_LABELS[metric] ?? metric}</td>
                          <td className="px-4 py-2">{DIRECTION_LABELS[direction] ?? direction}</td>
                          <td className="px-4 py-2 text-right font-mono">{d.decided}</td>
                          <td className="px-4 py-2 text-right font-mono">{d.hits}</td>
                          <td className="px-4 py-2 text-right font-mono">
                            {d.decided ? `${Math.round((d.hits / d.decided) * 100)}%` : "—"}
                          </td>
                          <td className="px-4 py-2 text-right font-mono">
                            {d.expected_rate != null
                              ? `${Math.round(d.expected_rate * 100)}%（n=${d.baseline_sample}）`
                              : "样本不足"}
                          </td>
                          <td className={`px-4 py-2 text-right font-mono ${(d.edge ?? 0) > 0 ? "text-emerald-600" : (d.edge ?? 0) < 0 ? "text-red-600" : ""}`}>
                            {d.edge != null ? (d.edge > 0 ? `+${d.edge}` : d.edge) : "—"}
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
                <p className="border-t bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
                  edge = 实际命中 − 已决 × 基准发生率：正数才说明预判比「历史自然出现频率」更准；
                  基准需 ≥12 个可比历史日样本。迟写条件对账但不计战绩。
                </p>
              </div>
            )}
          </section>
        </>
      )}
    </AccountPage>
  );
}
