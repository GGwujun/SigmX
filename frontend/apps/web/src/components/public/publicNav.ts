/** 公共站导航项：AI 发现沉浸式侧栏与内容页顶栏共用一份真源。 */
import { Blocks, Database, Globe2, Monitor, ScanSearch, Sparkles, Tag, type LucideIcon } from "lucide-react";

export interface PublicNavItem {
  to: string;
  label: string;
  active: boolean;
  /** 侧栏一级行的图标（内容页顶栏纯文字链接，不用它）。 */
  icon: LucideIcon;
}

export function publicNavItems(pathname: string): PublicNavItem[] {
  return [
    { to: "/", label: "AI 发现", active: pathname === "/" || ["/query/", "/stock/", "/fund/", "/research/"].some(prefix => pathname.startsWith(prefix)), icon: Sparkles },
    { to: "/intelligence", label: "情报搜索", active: pathname.startsWith("/intelligence"), icon: ScanSearch },
    { to: "/global-events", label: "全球事件", active: pathname.startsWith("/global-events"), icon: Globe2 },
    { to: "/skills", label: "投研 Skills", active: pathname.startsWith("/skills"), icon: Blocks },
    { to: "/product/desktop", label: "Desktop", active: pathname.startsWith("/product/desktop"), icon: Monitor },
    { to: "/product/data-hub", label: "Data Hub", active: pathname.startsWith("/product/data-hub") || pathname.startsWith("/docs/data-hub"), icon: Database },
    { to: "/pricing", label: "套餐", active: pathname.startsWith("/pricing"), icon: Tag },
  ];
}
