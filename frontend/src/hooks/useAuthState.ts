import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  clearAuth, disclaimerAccepted as disclaimerAcceptedFn,
  isAuthenticated, setToken, setUser, type AuthUser,
} from "@/lib/apiAuth";
import { restoreDesktopConnectedSession } from "@/lib/desktopConnectedSession";

declare global {
  interface Window {
    sigmxDesktop?: {
      isDesktop: boolean;
      checkForUpdates?: () => Promise<{ ok: boolean; version?: string }>;
      quitAndInstall?: () => Promise<void>;
      onUpdateAvailable?: (cb: (info: { version: string; releaseNotes?: string; releaseDate?: string }) => void) => () => void;
      onUpdateNotAvailable?: (cb: (info: { version: string }) => void) => () => void;
      onUpdateProgress?: (cb: (p: { percent: number; transferred: number; total: number; bytesPerSecond: number }) => void) => () => void;
      onUpdateDownloaded?: (cb: (info: { version: string; releaseNotes?: string; releaseDate?: string }) => void) => () => void;
      onUpdateError?: (cb: (err: { message: string }) => void) => () => void;
      // Cloud account (Task 9) — encrypted-at-rest bridge.
      cloudAccountLoad?: () => Promise<{
        refresh_token?: string;
        device_id?: string;
        account_email?: string;
        expires_at?: string;
      } | null>;
      cloudAccountSave?: (data: {
        refresh_token: string;
        device_id?: string;
        account_email?: string;
        expires_at?: string;
      }) => Promise<boolean>;
      cloudAccountClear?: () => Promise<boolean>;
      cloudAccountOpenAuthorization?: (url: string) => Promise<boolean>;
    };
  }
}

function isDesktopMode(): boolean {
  return !!window.sigmxDesktop?.isDesktop;
}

/**
 * Auth state for the route guard.
 *
 * On mount: if a token is present, validate it via /auth/me.
 * In desktop mode (Electron): auto-fetch a desktop session token so the
 * app skips the login page.
 *  - valid → authed=true, refresh local user (source of truth for disclaimer)
 *  - invalid/expired → clear auth, authed=false (guard redirects to /login)
 *
 * `recheck()` re-reads the local user (used by DisclaimerModal after accept
 * to drop the modal).
 */
export function useAuthState() {
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(false);
  // bump to force re-read of disclaimerAccepted() (localStorage-derived)
  const [, setBump] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 1) Already have a valid token — validate and proceed.
      if (isAuthenticated()) {
        try {
          const user: AuthUser = await api.getMe();
          if (cancelled) return;
          setUser(user);
          setAuthed(true);
          if (isDesktopMode()) void restoreDesktopConnectedSession().catch(() => undefined);
        } catch {
          if (cancelled) return;
          clearAuth();
          setAuthed(false);
        } finally {
          if (!cancelled) setLoading(false);
        }
        return;
      }

      // 2) Desktop mode: auto-fetch a session token so the user skips login.
      if (isDesktopMode()) {
        try {
          const res = await api.desktopSession();
          if (cancelled) return;
          setToken(res.token);
          setUser(res.user);
          setAuthed(true);
          void restoreDesktopConnectedSession().catch(() => undefined);
        } catch {
          if (cancelled) return;
          // Desktop session failed — fall through to login page.
          setAuthed(false);
        } finally {
          if (!cancelled) setLoading(false);
        }
        return;
      }

      // 3) No token, not desktop — show login page.
      setAuthed(false);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const recheck = useCallback(() => {
    // DisclaimerModal calls this after accept; user is already updated in
    // localStorage by the modal. Bump to re-derive disclaimerAccepted.
    setBump(b => b + 1);
  }, []);

  return {
    loading,
    authed,
    // getToken() is read live so logout elsewhere is respected; disclaimer
    // acceptance is derived from the freshly-stored user.
    disclaimerAccepted: authed ? disclaimerAcceptedFn() : false,
    recheck,
  };
}
