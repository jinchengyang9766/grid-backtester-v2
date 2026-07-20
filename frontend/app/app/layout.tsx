import type { Metadata } from "next";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppHeader } from "@/components/layout/app-header";

export const metadata: Metadata = {
  title: "Workspace",
};

export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // Unauthenticated visitors land on /login?next=/app and return here.
    <AuthGuard redirectPath="/app">
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        {children}
      </div>
    </AuthGuard>
  );
}
