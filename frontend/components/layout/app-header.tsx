"use client";

import { LogoutButton } from "@/components/auth/logout-button";
import { useAuth } from "@/lib/auth/use-auth";

export function AppHeader() {
  const { user } = useAuth();

  return (
    <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Grid Backtester
          </p>
          {user && (
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Signed in as <span className="font-medium">{user.email}</span>
            </p>
          )}
        </div>
        <LogoutButton />
      </div>
    </header>
  );
}
