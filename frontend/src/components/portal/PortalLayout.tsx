/**
 * Light portal shell for browser users (dual-shell design): a slim header
 * (logo / optional admin entry / logout) around the account <Outlet/>.
 * The desktop client keeps the heavy workbench `Layout`; browsers get this.
 */
import { Link, Outlet } from "react-router-dom";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { getUser } from "@/lib/apiAuth";

export function PortalLayout() {
  const user = getUser();

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-40 border-b bg-background shadow-sm">
        <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <Link to="/me" aria-label="SigmX" className="flex items-center gap-2 font-bold">
            <SigmXLogo className="h-6 w-6" />
            <span>SigmX</span>
          </Link>
          <div className="flex items-center gap-2">
            {user && <AccountMenu user={user} />}
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t py-6 text-center text-xs text-muted-foreground">
        <div className="mx-auto max-w-6xl px-4">
          SigmX · 仅供学习研究，不构成投资建议 · © {new Date().getFullYear()}
        </div>
      </footer>
    </div>
  );
}
