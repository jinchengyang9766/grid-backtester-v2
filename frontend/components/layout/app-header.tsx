"use client";

import { LogoutButton } from "@/components/auth/logout-button";
import { useAuth } from "@/lib/auth/use-auth";

export function AppHeader() {
  const { user } = useAuth();

  return (
    <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      {/* Visible only once focused, so keyboard users can bypass the header. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-sky-700 focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Skip to main content
      </a>
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
