import { Link, NavLink, Outlet } from "react-router-dom";
import { Activity, Bot, BookOpenText, Boxes, CircleDollarSign, Database, FileClock, Headphones, LayoutDashboard, Settings, Users } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { getUser } from "@/lib/apiAuth";
import { cn } from "@/lib/utils";

const MODULES = [
  { to: "/admin", label: "总览", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "用户", icon: Users },
  { to: "/admin/orders", label: "订单与兑换", icon: CircleDollarSign },
  { to: "/admin/plans", label: "套餐与商品", icon: Boxes },
  { to: "/admin/data-hub", label: "Data Hub", icon: Database },
  { to: "/admin/ai", label: "AI 投研配置", icon: Bot },
  { to: "/admin/content", label: "内容运营", icon: BookOpenText },
  { to: "/admin/support", label: "客服工单", icon: Headphones },
  { to: "/admin/audit", label: "审计日志", icon: FileClock },
  { to: "/admin/system", label: "系统设置", icon: Settings },
] as const;

export function AdminLayout() {
  const user = getUser();
  return <div className="min-h-screen bg-muted/30">
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur"><div className="flex h-14 items-center justify-between px-4 lg:px-6"><Link to="/" className="flex items-center gap-2 font-semibold"><SigmXLogo className="h-6 w-6" /><span>SigmX 运营后台</span><span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">ADMIN</span></Link><div className="flex items-center gap-3"><Link to="/" className="text-xs text-muted-foreground hover:text-foreground">返回官网</Link>{user && <AccountMenu user={user} />}</div></div></header>
    <div className="grid min-h-[calc(100vh-3.5rem)] lg:grid-cols-[220px_1fr]">
      <aside className="border-b bg-background p-3 lg:border-b-0 lg:border-r"><nav aria-label="运营模块" className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-1">{MODULES.map(({ to, label, icon: Icon, ...item }) => <NavLink key={to} to={to} end={"end" in item ? item.end : false} className={({ isActive }) => cn("flex items-center gap-2 rounded-md px-3 py-2 text-sm", isActive ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}><Icon className="h-4 w-4" />{label}</NavLink>)}</nav><div className="mt-4 hidden rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground lg:block"><div className="flex items-center gap-2 font-medium text-foreground"><Activity className="h-3.5 w-3.5 text-emerald-500" />系统运行正常</div><p className="mt-1">关键操作均记录审计日志。</p></div></aside>
      <main className="min-w-0"><Outlet /></main>
    </div>
  </div>;
}
