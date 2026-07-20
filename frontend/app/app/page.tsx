"use client";

/**
 * Authenticated workspace overview.
 *
 * A foundation placeholder: it shows only real session information. No
 * dataset counts, backtest summaries, or sample figures are invented, because
 * fabricated financial numbers in a backtesting tool are actively misleading.
 */

import { AppNavigation } from "@/components/layout/app-navigation";
import { useAuth } from "@/lib/auth/use-auth";

export default function WorkspacePage() {
  const { user } = useAuth();

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Workspace</h1>
      <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
        Your workspace is ready
        {user ? (
          <>
            , <span className="font-medium">{user.email}</span>
          </>
        ) : null}
        . Dataset import and backtesting arrive in the next steps.
      </p>

      <div className="mt-8 max-w-md">
        <AppNavigation />
      </div>
    </main>
  );
}
