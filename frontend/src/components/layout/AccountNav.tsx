/**
 * Sub-navigation between the account pages. Kept as a standalone component so
 * each account sub-page can render it without touching the shared Layout or the
 * existing Account.tsx. Links are relative to /account/*.
 */
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const ITEMS = [
  { to: "/account", label: "个人中心", end: true },
  { to: "/account/subscription", label: "套餐与激活", end: false },
  { to: "/account/credits", label: "积分", end: false },
  { to: "/account/orders", label: "订单", end: false },
  { to: "/account/devices", label: "设备", end: false },
];

export function AccountNav() {
  return (
    <nav className="flex flex-wrap gap-1 border-b pb-2">
      {ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
