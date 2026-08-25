/**
 * Devices page — list linked desktop devices and revoke one.
 * GET /api/devices + POST /api/devices/revoke. The device-code *linking* flow
 * (Task 9: start device flow in the desktop, approve in browser) lives on the
 * desktop side; this page manages already-linked devices.
 */
import { useCallback, useEffect, useState } from "react";
import { Laptop, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { AccountPage } from "@/components/layout/AccountPage";
import { getMyEntitlements, listDevices, revokeDevice, type DeviceItem } from "@/lib/productApi";
import { cn } from "@/lib/utils";

function shortDateTime(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function DevicesPage() {
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [deviceLimit, setDeviceLimit] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [devs, ent] = await Promise.all([listDevices(), getMyEntitlements()]);
      setDevices(devs);
      const limit = ent.entitlements["desktop.device_limit"];
      setDeviceLimit(typeof limit === "number" ? limit : 1);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载设备失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const doRevoke = async (deviceId: string, name: string) => {
    if (revokingId) return;
    if (!window.confirm(`确认解绑设备「${name}」？解绑后该设备的刷新令牌立即失效。`)) return;
    setRevokingId(deviceId);
    try {
      await revokeDevice(deviceId);
      toast.success("已解绑设备");
      await reload();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "解绑失败");
    } finally {
      setRevokingId(null);
    }
  };

  const active = devices.filter((d) => !d.revoked_at);
  const revoked = devices.filter((d) => d.revoked_at);

  return (
    <AccountPage>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">设备管理</h1>
          <p className="text-xs text-muted-foreground">
            已链接 {active.length} / {deviceLimit} 台设备
          </p>
        </div>
        <button onClick={reload} className="rounded-lg p-2 hover:bg-muted" title="刷新">
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      {loading ? (
        <div className="flex items-center justify-center py-10 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载设备…
        </div>
      ) : (
        <>
          <section className="space-y-2">
            <h2 className="text-sm font-semibold">已链接设备</h2>
            {active.length === 0 ? (
              <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
                暂无已链接设备。在桌面端通过设备授权流程登录 SigmX 云账户即可链接。
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
                      <div className="text-xs text-muted-foreground">
                        链接于 {shortDateTime(d.created_at)}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => doRevoke(d.id, d.name)}
                    disabled={revokingId === d.id}
                    className={cn(
                      "inline-flex h-8 items-center gap-1 rounded-md border px-3 text-xs",
                      "border-destructive/30 text-destructive hover:bg-destructive/10",
                      "disabled:opacity-50",
                    )}
                  >
                    {revokingId === d.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                    解绑
                  </button>
                </div>
              ))
            )}
          </section>

          {revoked.length > 0 && (
            <section className="space-y-2 opacity-60">
              <h2 className="text-sm font-semibold">已解绑设备</h2>
              {revoked.map((d) => (
                <div key={d.id} className="flex items-center gap-3 rounded-xl border bg-card p-4">
                  <Laptop className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <div className="text-sm font-medium">{d.name}</div>
                    <div className="text-xs text-muted-foreground">
                      解绑于 {shortDateTime(d.revoked_at)}
                    </div>
                  </div>
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </AccountPage>
  );
}
