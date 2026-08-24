import type { ReactNode } from "react";

import { AccountNav } from "@/components/layout/AccountNav";

export function AccountPage({ children }: { children: ReactNode }) {
  return (
    <main aria-label="账户页面" className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <AccountNav />
      {children}
    </main>
  );
}
