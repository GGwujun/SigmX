import { memo, useCallback, useEffect, useState } from "react";
import {
  Activity,
  Power,
  PlugZap,
  ShieldCheck,
  Clock,
  Loader2,
  ChevronDown,
  CircleDot,
  CircleSlash,
  OctagonX,
} from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type LiveStatus,
  type LiveBrokerStatus,
  type LiveMandateLimits,
  type LiveAuthorizeResponse,
} from "@/lib/api";

interface Props {
  /** Shared `GET /live/status` snapshot, polled once by the parent (Agent.tsx).
   * `null` until the first poll resolves. */
  status: LiveStatus | null;
  /** True when the status endpoint is not wired on this backend (404/501) — hide. */
  unavailable?: boolean;
  /** When true, every broker's halted banner reflects the global kill switch. */
  halted?: boolean;
  /** Forces the parent to re-poll immediately (e.g. after a runner start/stop). */
  onRefresh: () => void;
}

function formatUsd(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatRelative(value: string | number | null | undefined): string {
  if (value == null || value === "") return "从未";
  const then = typeof value === "number"
    ? (value < 1_000_000_000_000 ? value * 1000 : value)
    : new Date(value).getTime();
  if (!Number.isFinite(then)) return "未知";
  const deltaSec = Math.round((Date.now() - then) / 1000);
  if (deltaSec < 0) return "刚刚";
  if (deltaSec < 60) return `${deltaSec} 秒前`;
  if (deltaSec < 3600) return `${Math.floor(deltaSec / 60)} 分钟前`;
  if (deltaSec < 86_400) return `${Math.floor(deltaSec / 3600)} 小时前`;
  return `${Math.floor(deltaSec / 86_400)} 天前`;
}

function formatCountdown(iso: string | undefined): { label: string; expired: boolean; soon: boolean } {
  if (!iso) return { label: "—", expired: false, soon: false };
  const target = new Date(iso).getTime();
  if (!Number.isFinite(target)) return { label: "未知", expired: false, soon: false };
  const deltaSec = Math.round((target - Date.now()) / 1000);
  if (deltaSec <= 0) return { label: "已过期", expired: true, soon: false };
  const days = Math.floor(deltaSec / 86_400);
  const hours = Math.floor((deltaSec % 86_400) / 3600);
  const minutes = Math.floor((deltaSec % 3600) / 60);
  const soon = deltaSec < 86_400;
  if (days > 0) return { label: `${days} 天 ${hours} 小时`, expired: false, soon };
  if (hours > 0) return { label: `${hours} 小时 ${minutes} 分钟`, expired: false, soon };
  return { label: `${minutes} 分钟`, expired: false, soon };
}

function summarizeLimits(limits: LiveMandateLimits | undefined): string {
  if (!limits) return "";
  const parts: string[] = [];
  if (limits.max_order_notional_usd != null) parts.push(`单笔 ≤${formatUsd(limits.max_order_notional_usd)}`);
  if (limits.max_trades_per_day != null) parts.push(`每日 ${limits.max_trades_per_day} 笔`);
  if (limits.max_leverage != null) parts.push(limits.max_leverage <= 1 ? "无杠杆" : `${limits.max_leverage} 倍杠杆`);
  return parts.join(" / ");
}

function fallbackAuthorizeInstruction(): string {
  return "运行 `vibe-trading connector list` 选择券商配置，然后在承载连接的桌面会话里执行 `vibe-trading connector authorize <profile>`。";
}

function BrokerRow({
  broker,
  halted,
  onRefresh,
}: {
  broker: LiveBrokerStatus;
  halted: boolean;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [authorizeHint, setAuthorizeHint] = useState<LiveAuthorizeResponse | null>(null);
  const [authorizeFailed, setAuthorizeFailed] = useState(false);
  const brokerKey = broker.auth.broker;
  const authorized = broker.auth.oauth_token_present;
  const runnerAlive = broker.runner?.alive ?? false;
  const mandate = broker.mandate ?? null;
  const countdown = formatCountdown(mandate?.expires_at);
  const authorizeInstruction = authorizeHint?.instruction
    ?? (authorizeFailed ? fallbackAuthorizeInstruction() : "正在加载连接器授权指引…");
  const authorizeNote = "OAuth 授权成功并提交授权委托前，连接器通道保持只读。";

  useEffect(() => {
    let cancelled = false;
    setAuthorizeHint(null);
    setAuthorizeFailed(false);
    if (authorized || !brokerKey) return () => { cancelled = true; };

    api.authorizeLive(brokerKey)
      .then((response) => {
        if (!cancelled) setAuthorizeHint(response);
      })
      .catch(() => {
        if (!cancelled) setAuthorizeFailed(true);
      });

    return () => { cancelled = true; };
  }, [authorized, brokerKey]);

  const toggleRunner = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (runnerAlive) {
        await api.stopLiveRunner(brokerKey);
        toast.success(`${brokerKey} 运行器已停止`);
      } else {
        await api.startLiveRunner(brokerKey);
        toast.success(`${brokerKey} 运行器已启动`);
      }
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "运行器控制失败");
    } finally {
      setBusy(false);
    }
  }, [brokerKey, busy, runnerAlive, onRefresh]);

  return (
    <div className="grid gap-2 rounded-lg border bg-muted/20 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-xs font-semibold capitalize text-foreground">{brokerKey}</span>
          {authorized ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-1.5 py-0.5 text-[10px] font-medium text-success">
              <ShieldCheck className="h-2.5 w-2.5" />
              已授权
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              <CircleSlash className="h-2.5 w-2.5" />
              未连接
            </span>
          )}
        </div>
      </div>

      {/* Connect-profile on-ramp for unauthorized brokers (C2). The OAuth bootstrap
          is a desktop-only CLI step (SPEC §4 headless behavior), so the web surface
          surfaces the discoverable instruction rather than driving the browser flow. */}
      {!authorized ? (
        <div className="grid gap-1.5 rounded-md border border-dashed border-primary/30 bg-primary/5 p-2">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-primary">
            <PlugZap className="h-3 w-3 shrink-0" />
            连接此配置以启用连接器运行时
          </div>
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            {authorizeInstruction}
          </p>
          {authorizeNote && (
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              {authorizeNote}
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md border bg-background/60 p-2">
              <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                <CircleDot className={["h-2.5 w-2.5", runnerAlive ? "text-success" : "text-muted-foreground"].join(" ")} />
                运行器
              </div>
              <div className={["mt-0.5 text-xs font-semibold", runnerAlive ? "text-success" : "text-muted-foreground"].join(" ")}>
                {runnerAlive ? "运行中" : "已停止"}
              </div>
            </div>
            <div className="rounded-md border bg-background/60 p-2">
              <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                <Activity className="h-2.5 w-2.5" />
                最近心跳
              </div>
              <div className="mt-0.5 text-xs font-medium text-foreground">
                {formatRelative(broker.runner?.last_tick)}
              </div>
            </div>
          </div>

          {mandate ? (
            <div className="rounded-md border bg-background/60 p-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <ShieldCheck className="h-2.5 w-2.5" />
                  有效授权
                </div>
                {mandate.expires_at && (
                  <span
                    className={[
                      "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                      countdown.expired
                        ? "bg-destructive/10 text-destructive"
                        : countdown.soon
                          ? "bg-warning/10 text-warning"
                          : "bg-muted text-muted-foreground",
                    ].join(" ")}
                    title={`到期时间 ${new Date(mandate.expires_at).toLocaleString()}`}
                  >
                    <Clock className="h-2.5 w-2.5" />
                    {countdown.expired ? "已过期" : `${countdown.label} 后到期`}
                  </span>
                )}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-foreground">
                {summarizeLimits(mandate.limits) || "限制信息不可用"}
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed bg-background/40 p-2 text-[10px] text-muted-foreground">
              暂无有效授权。请先让智能体提出授权方案，提交后再启动连接器运行时。
            </div>
          )}

          <div className="flex items-center justify-between gap-2">
            {halted ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-destructive">
                <OctagonX className="h-3 w-3" />
                已停机，运行器控制不可用
              </span>
            ) : (
              <span className="text-[10px] text-muted-foreground">
                {runnerAlive ? "授权范围内运行中" : "空闲"}
              </span>
            )}
            <button
              type="button"
              onClick={toggleRunner}
              disabled={busy || halted || !mandate}
              className={[
                "inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-40",
                runnerAlive
                  ? "border-destructive/40 text-destructive hover:bg-destructive/10"
                  : "border-primary/40 text-primary hover:bg-primary/10",
              ].join(" ")}
              title={runnerAlive ? "停止常驻运行器" : "启动常驻运行器"}
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Power className="h-3 w-3" />}
              {runnerAlive ? "停止运行器" : "启动运行器"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Persistent live-runtime status panel (SPEC §7.5 + audit C2).
 *
 * Renders the shared `GET /live/status` snapshot (polled once by Agent.tsx and passed
 * in as `status`, so the kill switch and this panel share a single poller). Per authorized
 * profile: runner running state, last heartbeat tick, the active mandate's limits, and an
 * expiry countdown. `onRefresh` asks the parent to re-poll after a runner start/stop. Unauthorized
 * profiles get a connector on-ramp so a web user can discover how to enable connector
 * runtime execution. Runner start/stop are privileged surface fetches (`api.startLiveRunner` /
 * `api.stopLiveRunner`), never chat messages. Collapses to a compact toggle.
 */
export const RunnerStatus = memo(function RunnerStatus({ status, unavailable, halted, onRefresh }: Props) {
  const [open, setOpen] = useState(false);

  if (unavailable) return null;
  if (!status || status.brokers.length === 0) return null;

  const isHalted = halted ?? status.global_halted;
  const anyRunning = status.brokers.some((b) => b.runner?.alive);
  const authorizedCount = status.brokers.filter((b) => b.auth.oauth_token_present).length;

  return (
    <div className="grid gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex max-w-full items-center gap-1.5 justify-self-start rounded-lg bg-primary/10 px-2.5 py-1 text-left text-xs font-medium text-primary transition-colors hover:bg-primary/15"
        aria-label="连接器运行状态"
        aria-expanded={open}
      >
        <Activity className="h-3 w-3 shrink-0" />
        <span className="shrink-0">连接器运行时</span>
        <span className="truncate text-muted-foreground">
          {authorizedCount > 0 ? `${authorizedCount} 个已连接` : "暂无连接器连接"}
        </span>
        {anyRunning && !isHalted && (
          <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-1.5 py-0.5 text-[10px] font-medium text-success">
            <CircleDot className="h-2.5 w-2.5" />
            运行中
          </span>
        )}
        {isHalted && (
          <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
            <OctagonX className="h-2.5 w-2.5" />
            已停机
          </span>
        )}
        <ChevronDown className={["h-3 w-3 shrink-0 transition-transform", open ? "rotate-180" : ""].join(" ")} aria-hidden="true" />
      </button>

      {open && (
        <div className="grid gap-2 rounded-xl border border-primary/20 bg-background/95 p-3 shadow-sm">
          {status.brokers.map((broker) => (
            <BrokerRow key={broker.auth.broker} broker={broker} halted={isHalted || broker.halted} onRefresh={onRefresh} />
          ))}
        </div>
      )}
    </div>
  );
});
