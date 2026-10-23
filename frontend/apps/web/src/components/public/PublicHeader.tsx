/**
 * Public-site top bar: logo + primary nav + CTA / account menu + mobile drawer.
 * Light variant rides above the content pages (sticky, bordered); dark variant
 * floats transparently over the immersive AI workspace's right column — no
 * border, no background, so the chat surface reads as one continuous pane.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { getUser, isAuthenticated } from "@/lib/apiAuth";

export function PublicHeader({ dark = false, ctaLabel = "注册体验", ctaTo = "/register" }: { dark?: boolean; ctaLabel?: string; ctaTo?: string }) {
  const { pathname } = useLocation();
  const signedIn = isAuthenticated();
  const user = getUser();
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => setMobileOpen(false), [pathname]);

  const links = [
    { to: "/", label: "AI 发现", active: pathname === "/" || ["/query/", "/stock/", "/fund/", "/research/"].some((prefix) => pathname.startsWith(prefix)) },
    { to: "/intelligence", label: "情报搜索", active: pathname.startsWith("/intelligence") },
    { to: "/global-events", label: "全球事件", active: pathname.startsWith("/global-events") },
    { to: "/skills", label: "投研 Skills", active: pathname.startsWith("/skills") },
    { to: "/product/desktop", label: "Desktop", active: pathname.startsWith("/product/desktop") },
    { to: "/product/data-hub", label: "Data Hub", active: pathname.startsWith("/product/data-hub") || pathname.startsWith("/docs/data-hub") },
    { to: "/pricing", label: "套餐", active: pathname.startsWith("/pricing") },
  ];

  return (
    <header className={dark ? "z-40" : "sticky top-0 z-40 border-b bg-background shadow-sm"}>
      <div data-testid="public-header-inner" className={`flex h-14 items-center justify-between px-5 sm:px-8 ${dark ? "" : "mx-auto max-w-[1440px] lg:px-10"}`}>
        <Link to="/" className={`flex items-center gap-2 font-bold ${dark ? "text-slate-50" : ""}`}>
          <SigmXLogo className="h-6 w-6" />
          <span>SigmX</span>
        </Link>
        <nav aria-label="主导航" className="hidden items-center gap-1 md:flex">
          {links.map((item) => <PublicNavLink key={item.to} to={item.to} active={item.active} dark={dark}>{item.label}</PublicNavLink>)}
        </nav>
        <div className="flex items-center gap-2">
          {signedIn && user ? <AccountMenu user={user} tone={dark ? "dark" : "light"} /> : <Link to={ctaTo} className="inline-flex h-8 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">{ctaLabel}</Link>}
          <button type="button" aria-label={mobileOpen ? "关闭导航" : "打开导航"} aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)} className={`grid h-9 w-9 place-items-center rounded-md border md:hidden ${dark ? "border-white/15 text-slate-300 hover:bg-white/[0.06]" : ""}`}>{mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}</button>
        </div>
      </div>
      {mobileOpen && (
        <nav aria-label="移动导航" className={`border-t p-3 md:hidden ${dark ? "border-white/[0.07] bg-[#0d1219]" : "bg-background"}`}>
          <div className={`grid gap-1 ${dark ? "" : "mx-auto max-w-[1440px]"}`}>
            {links.map((item) => <Link key={item.to} to={item.to} aria-current={item.active ? "page" : undefined} className={`rounded-md px-3 py-2.5 text-sm ${item.active ? (dark ? "bg-teal-400/10 font-semibold text-teal-200" : "bg-primary/10 font-semibold text-primary") : dark ? "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100" : "text-muted-foreground hover:bg-muted"}`}>{item.label}</Link>)}
          </div>
        </nav>
      )}
    </header>
  );
}

function PublicNavLink({ to, active, dark, children }: { to: string; active: boolean; dark?: boolean; children: ReactNode }) {
  return <Link to={to} aria-current={active ? "page" : undefined} className={`relative inline-flex items-center rounded-md px-2.5 py-1.5 text-sm transition ${active ? (dark ? "bg-teal-400/10 font-semibold text-teal-200" : "bg-primary/10 font-semibold text-primary") : dark ? "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>{children}{active && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-primary" />}</Link>;
}
