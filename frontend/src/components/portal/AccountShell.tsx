/**
 * Account-area shell selector (dual-shell design): the `/account/*` pages are
 * shared between the desktop client and browser visitors — the desktop keeps
 * the heavy workbench `Layout` (sidebar, agent sessions), browsers get the
 * light `PortalLayout`.
 */
import { Layout } from "@/components/layout/Layout";
import { isDesktopMode } from "@/lib/desktop";
import { PortalLayout } from "./PortalLayout";

export function AccountShell() {
  return isDesktopMode() ? <Layout /> : <PortalLayout />;
}
