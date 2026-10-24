/**
 * Public-site layout shell (design §7.1): logo + top nav + a CTA, with a
 * <Outlet/> for the page body and a slim footer. Used by the acquisition pages
 * (landing, pricing, product pages) — no auth, no sidebar.
 */
import type { ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { PublicAppShell } from "@/components/public/PublicAppShell";
import { PublicHeader } from "@/components/public/PublicHeader";

export interface PublicLayoutProps {
  /** Optional override of the primary call-to-action (defaults to 注册体验). */
  ctaLabel?: string;
  ctaTo?: string;
  children?: ReactNode;
}

/** 并入沉浸左栏壳的内容页（与聊天页同一套 ChatGPT 式布局）。 */
const APP_SHELL_EXACT = new Set(["/intelligence", "/global-events", "/skills", "/product/desktop", "/product/data-hub", "/pricing"]);
const APP_SHELL_PREFIXES = ["/skills/", "/stock/", "/fund/"];
const isAppShellRoute = (pathname: string) => APP_SHELL_EXACT.has(pathname) || APP_SHELL_PREFIXES.some(prefix => pathname.startsWith(prefix));

export function PublicLayout({ ctaLabel = "注册体验", ctaTo = "/register" }: PublicLayoutProps) {
  const { pathname } = useLocation();
  // 沉浸态：根路径（AI 发现聊天工作台）与内容页（情报搜索/全球事件/Skills/
  // 产品与价格/个股基金）一律左栏常驻 + 右侧内容——不再回到上下堆叠布局。
  // /query /research/* /download /docs/* 保持浅色顶栏 + 页脚的常规布局。
  if (pathname === "/") {
    return <div className="flex min-h-dvh flex-col bg-white"><main className="flex flex-1 flex-col"><Outlet /></main></div>;
  }
  if (isAppShellRoute(pathname)) {
    return <div className="flex min-h-dvh flex-col bg-white"><main className="flex flex-1 flex-col"><PublicAppShell><Outlet /></PublicAppShell></main></div>;
  }
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <PublicHeader ctaLabel={ctaLabel} ctaTo={ctaTo} />
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t py-6 text-center text-xs text-muted-foreground">
        <div className="mx-auto max-w-[1440px] px-5 sm:px-8 lg:px-10">
          SigmX · 产品分离、平台能力共享 · © {new Date().getFullYear()}
        </div>
      </footer>
    </div>
  );
}
