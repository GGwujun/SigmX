/**
 * Desktop / browser mode detection + post-login routing target.
 *
 * The SPA serves two audiences: the Electron desktop client (loads this same
 * bundle via `http://localhost:8899/`, with `window.sigmxDesktop` injected by
 * preload — the Window type lives in `hooks/useAuthState.ts`) and plain web
 * visitors. Login/registration sends desktop users to the heavy workbench
 * (`/app`) and browsers to the light portal (`/portal`).
 */

/** True when running inside the Electron desktop client. */
export function isDesktopMode(): boolean {
  return !!window.sigmxDesktop?.isDesktop;
}

/** Where to navigate after a successful login/registration. */
export function postLoginTarget(): string {
  return isDesktopMode() ? "/app" : "/portal";
}
