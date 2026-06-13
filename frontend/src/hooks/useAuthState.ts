import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  clearAuth, disclaimerAccepted as disclaimerAcceptedFn,
  getToken, isAuthenticated, setUser, type AuthUser,
} from "@/lib/apiAuth";

/**
 * Auth state for the route guard.
 *
 * On mount: if a token is present, validate it via /auth/me.
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
      if (!isAuthenticated()) {
        setAuthed(false);
        setLoading(false);
        return;
      }
      try {
        const user: AuthUser = await api.getMe();
        if (cancelled) return;
        setUser(user);
        setAuthed(true);
      } catch {
        if (cancelled) return;
        // token invalid/expired → force re-login
        clearAuth();
        setAuthed(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
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
