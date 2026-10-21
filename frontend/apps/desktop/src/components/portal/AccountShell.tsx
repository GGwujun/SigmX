/**
 * Account-area shell selector (dual-shell design): the `/account/*` pages are
 * served to both the Electron client and plain browsers — the client keeps
 * the heavy workbench `Layout` (sidebar, agent sessions), browsers get the
 * light `PortalLayout`.
 */
import { isDesktopMode } from "@/lib/desktop";
import { Layout } from "@/components/layout/Layout";
import { PortalLayout } from "./PortalLayout";

export function AccountShell() {
  if (isDesktopMode()) {
    return <Layout />;
  }
  return <PortalLayout />;
}
