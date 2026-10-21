/**
 * Desktop device-authorization flow hook (Task 9).
 *
 * Drives the client side of the device-code flow:
 *   start() → server returns device_code + user_code + verification_url
 *   the user approves in a browser (the app opens verification_url)
 *   a timer polls /api/devices/authorize/poll every `interval` seconds
 *   on "approved" → persist the rotated refresh token via Electron IPC
 *
 * Browser-only environments (no window.sigmxDesktop) get a no-op hook so the
 * same component renders safely in both web and desktop.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  pollDeviceAuthorize,
  createDesktopDataHubSession,
  startDeviceAuthorize,
  type DeviceAuthorizeStart,
} from "@/lib/productApi";
import { setDataMode, setDesktopDataHubSessionKey } from "@/lib/dataMode";
import { setDesktopCloudAccessToken } from "@/lib/desktopConnectedSession";

export type FlowPhase = "idle" | "pending" | "approved" | "expired" | "error";

export interface DesktopDeviceFlowState {
  phase: FlowPhase;
  started: DeviceAuthorizeStart | null;
  error: string | null;
  /** Begin the flow. Returns the started codes (or throws). */
  start: (deviceName: string, fingerprintHash: string) => Promise<void>;
  /** Cancel any in-flight polling. */
  cancel: () => void;
}

interface DesktopBridge {
  cloudAccountSave?: (data: {
    refresh_token: string;
    device_id?: string;
    account_email?: string;
    expires_at?: string;
  }) => Promise<boolean>;
  cloudAccountOpenAuthorization?: (url: string) => Promise<boolean>;
}

function getBridge(): DesktopBridge | null {
  if (typeof window === "undefined") return null;
  return (window.sigmxDesktop as unknown as DesktopBridge) ?? null;
}

export function useDesktopDeviceFlow(onApproved?: () => void): DesktopDeviceFlowState {
  const [phase, setPhase] = useState<FlowPhase>("idle");
  const [started, setStarted] = useState<DeviceAuthorizeStart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    clearTimer();
    setPhase("idle");
    setStarted(null);
  }, [clearTimer]);

  const poll = useCallback(
    async (deviceCode: string, intervalSeconds: number) => {
      if (cancelledRef.current) return;
      try {
        const result = await pollDeviceAuthorize(deviceCode);
        if (cancelledRef.current) return;
        if (result.status === "approved" && result.refresh_token && result.access_token && result.device_id) {
          clearTimer();
          const bridge = getBridge();
          await bridge?.cloudAccountSave?.({
            refresh_token: result.refresh_token,
            device_id: result.device_id,
          });
          const session = await createDesktopDataHubSession(result.device_id, result.access_token);
          setDesktopCloudAccessToken(result.access_token);
          setDesktopDataHubSessionKey(session.plaintext);
          setDataMode("connected");
          setPhase("approved");
          onApproved?.();
          return;
        }
        if (result.status === "expired") {
          clearTimer();
          setPhase("expired");
          return;
        }
        // pending → schedule next poll.
        timerRef.current = setTimeout(
          () => void poll(deviceCode, intervalSeconds),
          Math.max(1, intervalSeconds) * 1000,
        );
      } catch (e) {
        if (cancelledRef.current) return;
        clearTimer();
        setError(e instanceof Error ? e.message : "轮询失败");
        setPhase("error");
      }
    },
    [clearTimer, onApproved],
  );

  const start = useCallback(
    async (deviceName: string, fingerprintHash: string) => {
      cancelledRef.current = false;
      clearTimer();
      setError(null);
      setPhase("pending");
      try {
        const s = await startDeviceAuthorize(deviceName, fingerprintHash);
        if (cancelledRef.current) return;
        setStarted(s);
        // Open the browser verification URL for the user.
        const bridge = getBridge();
        await bridge?.cloudAccountOpenAuthorization?.(s.verification_url);
        // Begin polling.
        timerRef.current = setTimeout(
          () => void poll(s.device_code, s.interval_seconds),
          Math.max(1, s.interval_seconds) * 1000,
        );
      } catch (e) {
        if (cancelledRef.current) return;
        setError(e instanceof Error ? e.message : "启动授权失败");
        setPhase("error");
      }
    },
    [clearTimer, poll],
  );

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
  }, [clearTimer]);

  return { phase, started, error, start, cancel };
}
