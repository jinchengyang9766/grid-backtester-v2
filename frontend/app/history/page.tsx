import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthGuard } from "@/components/auth/auth-guard";
import { BacktestHistoryPage } from "@/components/history/backtest-history-page";
import { AppHeader } from "@/components/layout/app-header";
import { LoadingState } from "@/components/ui/loading-state";

export const metadata: Metadata = {
  title: "Backtest history",
};

export default function HistoryPage() {
  return (
    // Unauthenticated visitors go to /login?next=%2Fhistory and return here.
    <AuthGuard redirectPath="/history">
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Backtest history</h1>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                Every backtest you have run, newest first.
              </p>
            </div>
            <Link
              href="/backtest/new"
              className="inline-flex items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            >
              New backtest
            </Link>
          </div>

          <div className="mt-8">
            {/* Filters live in the query string, so this reads searchParams. */}
            <Suspense fallback={<LoadingState label="Loading backtests…" />}>
              <BacktestHistoryPage />
            </Suspense>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
