/**
 * Public-site layout shell (design §7.1): logo + top nav + a CTA, with a
 * <Outlet/> for the page body and a slim footer. Used by the acquisition pages
 * (landing, pricing, product pages) — no auth, no sidebar.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { getUser, isAuthenticated } from "@/lib/apiAuth";

export interface PublicLayoutProps {
  /** Optional override of the primary call-to-action (defaults to 注册体验). */
  ctaLabel?: string;
  ctaTo?: string;
  children?: ReactNode;
}

export function PublicLayout({ ctaLabel = "注册体验", ctaTo = "/register" }: PublicLayoutProps) {
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
  // 沉浸态：仅根路径（AI 发现聊天工作台）整页转深色，顶栏/页脚随之成为同一块连续表面
  // （学习 claude.ai/Linear）。/query /stock 等子页是浅色内容页，保持浅色铬件。
  // 铬件高度严格不变：h-14+border-b / py-6+text-xs。
  const immersive = pathname === "/";

  return (
    <div className={`flex min-h-screen flex-col ${immersive ? "bg-[#0b0f14]" : "bg-background"}`}>
      <header className={`sticky top-0 z-40 border-b ${immersive ? "border-white/[0.07] bg-[#0d1219]/95 shadow-none backdrop-blur" : "bg-background shadow-sm"}`}>
        <div data-testid="public-header-inner" className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-10">
          <Link to="/" className={`flex items-center gap-2 font-bold ${immersive ? "text-slate-50" : ""}`}>
            <SigmXLogo className="h-6 w-6" />
            <span>SigmX</span>
          </Link>
          <nav aria-label="主导航" className="hidden items-center gap-1 md:flex">
            {links.map((item) => <PublicNavLink key={item.to} to={item.to} active={item.active} dark={immersive}>{item.label}</PublicNavLink>)}
          </nav>
          <div className="flex items-center gap-2">
            {signedIn && user ? <AccountMenu user={user} tone={immersive ? "dark" : "light"} /> : <Link to={ctaTo} className="inline-flex h-8 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">{ctaLabel}</Link>}
            <button type="button" aria-label={mobileOpen ? "关闭导航" : "打开导航"} aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)} className={`grid h-9 w-9 place-items-center rounded-md border md:hidden ${immersive ? "border-white/15 text-slate-300 hover:bg-white/[0.06]" : ""}`}>{mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}</button>
          </div>
        </div>
        {mobileOpen && <nav aria-label="移动导航" className={`border-t p-3 md:hidden ${immersive ? "border-white/[0.07] bg-[#0d1219]" : "bg-background"}`}><div className="mx-auto grid max-w-[1440px] gap-1">{links.map((item) => <Link key={item.to} to={item.to} aria-current={item.active ? "page" : undefined} className={`rounded-md px-3 py-2.5 text-sm ${item.active ? (immersive ? "bg-teal-400/10 font-semibold text-teal-200" : "bg-primary/10 font-semibold text-primary") : immersive ? "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100" : "text-muted-foreground hover:bg-muted"}`}>{item.label}</Link>)}</div></nav>}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      {/* 沉浸态（AI 发现工作台）不渲染页脚：聊天画布直接铺到视口底，页脚只留给内容页 */}
      {!immersive && (
        <footer className="border-t py-6 text-center text-xs text-muted-foreground">
          <div className="mx-auto max-w-[1440px] px-5 sm:px-8 lg:px-10">
            SigmX · 产品分离、平台能力共享 · © {new Date().getFullYear()}
          </div>
        </footer>
      )}
    </div>
  );
}

function PublicNavLink({ to, active, dark, children }: { to: string; active: boolean; dark?: boolean; children: ReactNode }) {
  return <Link to={to} aria-current={active ? "page" : undefined} className={`relative inline-flex items-center rounded-md px-2.5 py-1.5 text-sm transition ${active ? (dark ? "bg-teal-400/10 font-semibold text-teal-200" : "bg-primary/10 font-semibold text-primary") : dark ? "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>{children}{active && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-primary" />}</Link>;
}
