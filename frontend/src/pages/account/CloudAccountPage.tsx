/**
 * Cloud-account / device authorization page (Task 9).
 *
 * Two roles on one page (design §3.1, §5.1):
 *  1. Browser approval — the user types the user_code shown by the desktop
 *     client and confirms; POST /api/devices/authorize/approve.
 *  2. Linked-device overview — already-linked devices with revoke.
 *
 * The desktop *start/poll* side runs through Electron IPC (Task 34, desktop/),
 * not here — the renderer never touches the filesystem.
 */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Loader2, ShieldCheck, Laptop, RefreshCw, Monitor } from "lucide-react";
import { toast } from "sonner";

import { AccountPage } from "@/components/layout/AccountPage";
import { ProductStatus } from "@/components/layout/ProductStatus";
import { useDesktopDeviceFlow } from "@/hooks/useDesktopDeviceFlow";
import { ApiError } from "@/lib/api";
import {
  approveDeviceAuthorize,
  getMyEntitlements,
  listDevices,
  revokeDevice,
  type DeviceItem,
} from "@/lib/productApi";

function shortDateTime(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function CloudAccountPage() {
  const [userCode, setUserCode] = useState("");
  const [approving, setApproving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Desktop-only: the client-side device-code flow (start → poll → persist).
  const isDesktop = typeof window !== "undefined" && !!window.sigmxDesktop?.isDesktop;
  const flow = useDesktopDeviceFlow(() => {
    toast.success("云账户已链接");
    setRefreshKey((k) => k + 1);
  });

  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [deviceLimit, setDeviceLimit] = useState(1);
  const [loading, setLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [devs, ent] = await Promise.all([listDevices(), getMyEntitlements()]);
      setDevices(devs);
      const limit = ent.entitlements["desktop.device_limit"];
      setDeviceLimit(typeof limit === "number" ? limit : 1);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  const doApprove = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = userCode.trim().toUpperCase();
    if (!trimmed || approving) return;
    setApproving(true);
    try {
      await approveDeviceAuthorize(trimmed);
      toast.success("已批准设备链接");
      setUserCode("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "批准失败");
    } finally {
      setApproving(false);
    }
  };

  const doRevoke = async (deviceId: string, name: string) => {
    if (revokingId) return;
    if (!window.confirm(`确认解绑设备「${name}」？`)) return;
    setRevokingId(deviceId);
    try {
      await revokeDevice(deviceId);
      toast.success("已解绑");
      setRefreshKey((k) => k + 1);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "解绑失败");
    } finally {
      setRevokingId(null);
    }
  };

  const active = devices.filter((d) => !d.revoked_at);

  return (
    <AccountPage>
      <header>
        <h1 className="flex items-center gap-2 text-lg font-bold">
          <ShieldCheck className="h-5 w-5 text-primary" /> 云账户 · 设备授权
        </h1>
        <p className="text-xs text-muted-foreground">
          在桌面客户端发起授权后，在此处输入显示的用户码完成链接
        </p>
      </header>

      <ProductStatus refreshKey={refreshKey} />

      {isDesktop && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Monitor className="h-4 w-4 text-primary" /> 链接这台设备（桌面端）
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            发起授权后，会打开浏览器让你确认。确认后这台桌面端会自动获得云账户访问凭证。
          </p>

          {flow.phase === "idle" || flow.phase === "error" ? (
            <button
              onClick={() => flow.start("SigmX Desktop", "desktop-fp")}
              className="mt-4 inline-flex h-10 items-center gap-1 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              发起授权
            </button>
          ) : flow.phase === "pending" && flow.started ? (
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                等待浏览器确认… 用户码：
                <code className="rounded bg-muted px-2 py-0.5 font-mono tracking-widest">
                  {flow.started.user_code}
                </code>
              </div>
              <button onClick={flow.cancel} className="text-xs text-muted-foreground underline">
                取消
              </button>
            </div>
          ) : flow.phase === "approved" ? (
            <p className="mt-4 text-sm text-emerald-600">✓ 已链接</p>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">授权已过期，请重新发起。</p>
          )}

          {flow.error && <p className="mt-2 text-xs text-destructive">{flow.error}</p>}
        </section>
      )}

      <section className="rounded-xl border bg-card p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-primary" /> 批准设备链接
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          桌面客户端会显示一个用户码（如 ABCD-EFGH）。输入它以把该设备链接到你的账户。
          套餐设备数上限：{deviceLimit} 台。
        </p>
        <form onSubmit={doApprove} className="mt-4 flex gap-2">
          <input
            value={userCode}
            onChange={(e) => setUserCode(e.target.value)}
            placeholder="ABCD-EFGH"
            autoComplete="off"
            spellCheck={false}
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm font-mono uppercase tracking-widest outline-none focus:ring-2 focus:ring-primary/40"
          />
          <button
            type="submit"
            disabled={approving || !userCode.trim()}
            className="inline-flex h-10 items-center justify-center gap-1 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {approving ? <Loader2 className="h-4 w-4 animate-spin" /> : "批准链接"}
          </button>
        </form>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">已链接设备（{active.length}/{deviceLimit}）</h2>
          <button
            onClick={() => {
              setLoading(true);
              setRefreshKey((k) => k + 1);
            }}
            className="rounded-lg p-2 hover:bg-muted"
            title="刷新"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        {loading ? (
          <div className="flex items-center py-6 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载…
          </div>
        ) : active.length === 0 ? (
          <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
            暂无已链接设备。
          </p>
        ) : (
          active.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between rounded-xl border bg-card p-4"
            >
              <div className="flex items-center gap-3">
                <Laptop className="h-5 w-5 text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium">{d.name}</div>
                  <div className="text-xs text-muted-foreground">链接于 {shortDateTime(d.created_at)}</div>
                </div>
              </div>
              <button
                onClick={() => doRevoke(d.id, d.name)}
                disabled={revokingId === d.id}
                className="inline-flex h-8 items-center rounded-md border border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50"
              >
                {revokingId === d.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "解绑"}
              </button>
            </div>
          ))
        )}
      </section>
    </AccountPage>
  );
}
