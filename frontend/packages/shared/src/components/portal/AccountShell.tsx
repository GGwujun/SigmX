/**
 * Account-area shell selector (dual-shell design): the `/account/*` pages are
 * shared between the desktop client and browser visitors — the desktop keeps
 * the heavy workbench `Layout` (sidebar, agent sessions), browsers get the
 * light `PortalLayout`. The heavy `Layout` lives in the desktop app and is
 * injected here so this package never depends on app code.
 */
import type { ComponentType } from "react";
import { isDesktopMode } from "@sigmx/api-client/desktop";
import { PortalLayout } from "./PortalLayout";

export function AccountShell({ desktopLayout }: { desktopLayout?: ComponentType }) {
  if (isDesktopMode() && desktopLayout) {
    const DesktopLayout = desktopLayout;
    return <DesktopLayout />;
  }
  return <PortalLayout />;
}
