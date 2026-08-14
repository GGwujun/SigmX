/**
 * Light portal shell for browser users (dual-shell design): a slim header
 * (logo / optional admin entry / logout) around the account <Outlet/>.
 * The desktop client keeps the heavy workbench `Layout`; browsers get this.
 */
import { Link, Outlet, useNavigate } from "react-router-dom";
import { LogOut, Settings2 } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { clearAuth, getUser, isAdmin } from "@/lib/apiAuth";

export function PortalLayout() {
  const navigate = useNavigate();
  const user = getUser();
  const admin = isAdmin();

  const logout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/portal" className="flex items-center gap-2 font-bold">
            <SigmXLogo className="h-6 w-6" />
            <span>SigmX</span>
          </Link>
          <div className="flex items-center gap-2">
            {user && <span className="hidden text-xs text-muted-foreground sm:inline">{user.email}</span>}
            {admin && (
              <Link
                to="/admin/operations"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                title="运营后台"
              >
                <Settings2 className="h-3.5 w-3.5" />
                运营后台
              </Link>
            )}
            <button
              type="button"
              onClick={logout}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              title="退出登录"
            >
              <LogOut className="h-3.5 w-3.5" />
              退出
            </button>
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
