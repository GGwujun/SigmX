/**
 * Public-site top bar for the content pages (query/stock/pricing/...): logo +
 * primary nav + CTA / account menu + mobile drawer. The immersive AI 发现
 * workspace (root path) does NOT render this header — its navigation lives in
 * the ChatGPT-style sidebar (see AIAnalysisShell).
 */
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { getUser, isAuthenticated } from "@/lib/apiAuth";
import { publicNavItems } from "@/components/public/publicNav";

export function PublicHeader({ ctaLabel = "注册体验", ctaTo = "/register" }: { ctaLabel?: string; ctaTo?: string }) {
  const { pathname } = useLocation();
  const signedIn = isAuthenticated();
  const user = getUser();
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => setMobileOpen(false), [pathname]);
  const links = publicNavItems(pathname);

  return (
    <header className="sticky top-0 z-40 border-b bg-background shadow-sm">
      <div data-testid="public-header-inner" className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-10">
        <Link to="/" className="flex items-center gap-2 font-bold">
          <SigmXLogo className="h-6 w-6" />
          <span>SigmX</span>
        </Link>
        <nav aria-label="主导航" className="hidden items-center gap-1 md:flex">
          {links.map((item) => <PublicNavLink key={item.to} to={item.to} active={item.active}>{item.label}</PublicNavLink>)}
        </nav>
        <div className="flex items-center gap-2">
          {signedIn && user ? <AccountMenu user={user} /> : <Link to={ctaTo} className="inline-flex h-8 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">{ctaLabel}</Link>}
          <button type="button" aria-label={mobileOpen ? "关闭导航" : "打开导航"} aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)} className="grid h-9 w-9 place-items-center rounded-md border md:hidden">{mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}</button>
        </div>
      </div>
      {mobileOpen && (
        <nav aria-label="移动导航" className="border-t bg-background p-3 md:hidden">
          <div className="mx-auto grid max-w-[1440px] gap-1">
            {links.map((item) => <Link key={item.to} to={item.to} aria-current={item.active ? "page" : undefined} className={`rounded-md px-3 py-2.5 text-sm ${item.active ? "bg-primary/10 font-semibold text-primary" : "text-muted-foreground hover:bg-muted"}`}>{item.label}</Link>)}
          </div>
        </nav>
      )}
    </header>
  );
}

function PublicNavLink({ to, active, children }: { to: string; active: boolean; children: ReactNode }) {
  return <Link to={to} aria-current={active ? "page" : undefined} className={`relative inline-flex items-center rounded-md px-2.5 py-1.5 text-sm transition ${active ? "bg-primary/10 font-semibold text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>{children}{active && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-primary" />}</Link>;
}
