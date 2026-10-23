/** 公共站导航项：AI 发现沉浸式侧栏与内容页顶栏共用一份真源。 */
export interface PublicNavItem {
  to: string;
  label: string;
  active: boolean;
}

export function publicNavItems(pathname: string): PublicNavItem[] {
  return [
    { to: "/", label: "AI 发现", active: pathname === "/" || ["/query/", "/stock/", "/fund/", "/research/"].some(prefix => pathname.startsWith(prefix)) },
    { to: "/intelligence", label: "情报搜索", active: pathname.startsWith("/intelligence") },
    { to: "/global-events", label: "全球事件", active: pathname.startsWith("/global-events") },
    { to: "/skills", label: "投研 Skills", active: pathname.startsWith("/skills") },
    { to: "/product/desktop", label: "Desktop", active: pathname.startsWith("/product/desktop") },
    { to: "/product/data-hub", label: "Data Hub", active: pathname.startsWith("/product/data-hub") || pathname.startsWith("/docs/data-hub") },
    { to: "/pricing", label: "套餐", active: pathname.startsWith("/pricing") },
  ];
}
