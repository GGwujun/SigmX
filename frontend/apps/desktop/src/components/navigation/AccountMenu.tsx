import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, ShieldCheck, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { clearAuth, type AuthUser } from "@/lib/apiAuth";

const ACCOUNT_LINKS = [
  { to: "/me", label: "个人中心" },
  { to: "/account", label: "账户与安全" },
  { to: "/account/subscription", label: "套餐与账单" },
  { to: "/account/data-hub", label: "Data Hub 控制台" },
  { to: "/account/devices", label: "Desktop 设备" },
] as const;

export function AccountMenu({ user }: { user: AuthUser }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const logout = () => {
    clearAuth();
    setOpen(false);
    navigate("/login", { replace: true });
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-9 max-w-56 items-center gap-2 rounded-full border bg-card px-2.5 text-sm font-medium shadow-sm hover:bg-muted"
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><UserRound className="h-3.5 w-3.5" /></span>
        <span className="hidden truncate sm:inline">{user.email}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-11 z-50 w-64 overflow-hidden rounded-xl border bg-background p-1.5 text-foreground shadow-2xl ring-1 ring-black/5">
          <div className="border-b px-3 py-2 sm:hidden"><p className="truncate text-xs text-muted-foreground">{user.email}</p></div>
          {ACCOUNT_LINKS.map((item) => <Link role="menuitem" key={item.to} to={item.to} onClick={() => setOpen(false)} className="block rounded-md px-3 py-2 text-sm hover:bg-muted">{item.label}</Link>)}
          {user.is_admin && <><div className="my-1 border-t" /><Link role="menuitem" to="/admin" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-muted"><ShieldCheck className="h-4 w-4 text-primary" />运营后台</Link></>}
          <div className="my-1 border-t" />
          <button role="menuitem" type="button" onClick={logout} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-destructive hover:bg-muted"><LogOut className="h-4 w-4" />退出登录</button>
        </div>
      )}
    </div>
  );
}
