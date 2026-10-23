/**
 * Public-site layout shell (design §7.1): logo + top nav + a CTA, with a
 * <Outlet/> for the page body and a slim footer. Used by the acquisition pages
 * (landing, pricing, product pages) — no auth, no sidebar.
 */
import type { ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { PublicHeader } from "@/components/public/PublicHeader";

export interface PublicLayoutProps {
  /** Optional override of the primary call-to-action (defaults to 注册体验). */
  ctaLabel?: string;
  ctaTo?: string;
  children?: ReactNode;
}

export function PublicLayout({ ctaLabel = "注册体验", ctaTo = "/register" }: PublicLayoutProps) {
  const { pathname } = useLocation();
  // 沉浸态：仅根路径（AI 发现聊天工作台）整页交给 AIAnalysisShell 做 ChatGPT 式
  // 左右布局——左栏从视口顶铺到底、顶栏渲染进右栏、无页脚。/query /stock 等
  // 内容页保持浅色顶栏 + 页脚的常规布局。
  if (pathname === "/") {
    return <div className="flex min-h-dvh flex-col bg-white"><main className="flex flex-1 flex-col"><Outlet /></main></div>;
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
