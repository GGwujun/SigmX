import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

export function PortalNav() {
  const { pathname } = useLocation();
  const active = pathname === "/me" || pathname.startsWith("/account");

  return (
    <nav aria-label="产品导航" className="flex flex-wrap items-center gap-1">
      <Link
        to="/me"
        aria-current={active ? "page" : undefined}
        className={cn(
          "rounded-md px-2.5 py-1.5 text-sm transition-colors",
          active
            ? "bg-primary/10 font-medium text-primary"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        个人中心
      </Link>
    </nav>
  );
}
