import { Link, NavLink } from "react-router-dom";

import { PUBLIC_PRODUCT_LINKS } from "@/components/navigation/productNavigation";
import { cn } from "@/lib/utils";

const PRIVATE_LINKS = [
  { to: "/me", label: "我的 SigmX", end: true },
  { to: "/account", label: "账户中心", end: false },
] as const;

export function PortalNav() {
  return (
    <nav aria-label="产品导航" className="flex flex-wrap items-center gap-1">
      {PRIVATE_LINKS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "rounded-md px-2.5 py-1.5 text-sm transition-colors",
              isActive
                ? "bg-primary/10 font-medium text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
      <span className="mx-1 hidden h-4 w-px bg-border lg:block" aria-hidden="true" />
      {PUBLIC_PRODUCT_LINKS.slice(0, 2).map((item) => (
        <Link
          key={item.to}
          to={item.to}
          title={item.description}
          className="hidden rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground lg:block"
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
