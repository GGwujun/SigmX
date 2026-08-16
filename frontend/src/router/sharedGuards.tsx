import { type ComponentType, type ReactNode, Suspense } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { DisclaimerModal } from "@/components/DisclaimerModal";
import { useAuthState } from "@/hooks/useAuthState";
import { isAdmin } from "@/lib/apiAuth";

export function PageLoader() {
  return <div className="flex h-[60vh] items-center justify-center text-muted-foreground">加载中…</div>;
}

export function wrap(Component: ComponentType): ReactNode {
  return <Suspense fallback={<PageLoader />}><Component /></Suspense>;
}

export function RequireAuth() {
  const { authed, disclaimerAccepted, recheck, loading } = useAuthState();
  if (loading) return <PageLoader />;
  if (!authed) return <Navigate to="/login" replace />;
  return <><Outlet />{!disclaimerAccepted && <DisclaimerModal onAccepted={recheck} />}</>;
}

export function RequireAdmin() {
  return isAdmin() ? <Outlet /> : <Navigate to="/" replace />;
}
