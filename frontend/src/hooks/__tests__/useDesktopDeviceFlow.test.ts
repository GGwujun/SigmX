import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useDesktopDeviceFlow } from "../useDesktopDeviceFlow";

// Fake the bridge + fetch; drive the polling with vitest fake timers.
function mockFetchByPath(map: Record<string, (url: string, init?: RequestInit) => unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      for (const key of Object.keys(map)) {
        if (url.includes(key)) {
          const body = map[key](url, init);
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => body,
          } as unknown as Response);
        }
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as unknown as Response);
    }),
  );
}

function installBridge() {
  const save = vi.fn().mockResolvedValue(true);
  const openAuth = vi.fn().mockResolvedValue(true);
  vi.stubGlobal("sigmxDesktop", { isDesktop: true, cloudAccountSave: save, cloudAccountOpenAuthorization: openAuth });
  return { save, openAuth };
}

describe("useDesktopDeviceFlow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("starts, opens the verification URL, and polls until approved", async () => {
    let pollCount = 0;
    mockFetchByPath({
      "/api/devices/authorize/start": () => ({
        device_code: "dc1",
        user_code: "ABCD-EFGH",
        verification_url: "https://app/verify?user_code=ABCD-EFGH",
        interval_seconds: 1,
        expires_in_seconds: 600,
      }),
      "/api/devices/authorize/poll": () => {
        pollCount += 1;
        // First poll pending, second approved.
        if (pollCount === 1) return { status: "pending", access_token: null, refresh_token: null, interval_seconds: 1 };
        return { status: "approved", access_token: "tok", refresh_token: "rfr_rotated", interval_seconds: 1 };
      },
    });
    const { save, openAuth } = installBridge();
    const onApproved = vi.fn();

    const { result } = renderHook(() => useDesktopDeviceFlow(onApproved));
    await act(async () => {
      await result.current.start("my-desk", "fp-1");
    });

    expect(result.current.phase).toBe("pending");
    expect(result.current.started?.user_code).toBe("ABCD-EFGH");
    expect(openAuth).toHaveBeenCalledWith("https://app/verify?user_code=ABCD-EFGH");

    // Run both scheduled polls (pending → approved) to completion.
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.phase).toBe("approved");
    expect(pollCount).toBe(2);
    expect(save).toHaveBeenCalledWith({ refresh_token: "rfr_rotated" });
    expect(onApproved).toHaveBeenCalled();
  });

  it("moves to expired when the server says so", async () => {
    mockFetchByPath({
      "/api/devices/authorize/start": () => ({
        device_code: "dc1",
        user_code: "ABCD-EFGH",
        verification_url: "https://app/verify",
        interval_seconds: 1,
        expires_in_seconds: 600,
      }),
      "/api/devices/authorize/poll": () => ({ status: "expired", access_token: null, refresh_token: null, interval_seconds: 1 }),
    });
    installBridge();
    const { result } = renderHook(() => useDesktopDeviceFlow());

    await act(async () => {
      await result.current.start("d", "fp");
    });
    await act(async () => {
      vi.advanceTimersByTimeAsync(1100);
    });
    expect(result.current.phase).toBe("expired");
  });

  it("cancel stops polling and resets to idle", async () => {
    mockFetchByPath({
      "/api/devices/authorize/start": () => ({
        device_code: "dc1",
        user_code: "ABCD-EFGH",
        verification_url: "https://app/verify",
        interval_seconds: 1,
        expires_in_seconds: 600,
      }),
      "/api/devices/authorize/poll": () => ({ status: "pending", access_token: null, refresh_token: null, interval_seconds: 1 }),
    });
    installBridge();
    const { result } = renderHook(() => useDesktopDeviceFlow());

    await act(async () => {
      await result.current.start("d", "fp");
    });
    act(() => result.current.cancel());
    expect(result.current.phase).toBe("idle");
    expect(result.current.started).toBeNull();
  });
});
