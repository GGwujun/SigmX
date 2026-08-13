/**
 * Public-site layout shell (design §7.1): logo + top nav + a CTA, with a
 * <Outlet/> for the page body and a slim footer. Used by the acquisition pages
 * (landing, pricing, product pages) — no auth, no sidebar.
 */
import { type ReactNode } from "react";
import { Link, Outlet } from "react-router-dom";

import { SigmXLogo } from "@/components/brand/SigmXLogo";

const NAV = [
  { to: "/product/data-hub", label: "Data Hub" },
  { to: "/product/desktop", label: "桌面端" },
  { to: "/pricing", label: "套餐" },
  { to: "/download", label: "下载" },
];

export interface PublicLayoutProps {
  /** Optional override of the primary call-to-action (defaults to 注册体验). */
  ctaLabel?: string;
  ctaTo?: string;
  children?: ReactNode;
}

export function PublicLayout({ ctaLabel = "注册体验", ctaTo = "/register" }: PublicLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2 font-bold">
            <SigmXLogo className="h-6 w-6" />
            <span>SigmX</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
            <Link
              to={ctaTo}
              className="ml-2 inline-flex h-8 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              {ctaLabel}
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t py-6 text-center text-xs text-muted-foreground">
        <div className="mx-auto max-w-6xl px-4">
          SigmX · 产品分离、平台能力共享 · © {new Date().getFullYear()}
        </div>
      </footer>
    </div>
  );
}
