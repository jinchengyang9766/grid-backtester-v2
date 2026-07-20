import type { Metadata } from "next";
import Link from "next/link";

import { AuthGuard } from "@/components/auth/auth-guard";
import { DatasetList } from "@/components/datasets/dataset-list";
import { AppHeader } from "@/components/layout/app-header";

export const metadata: Metadata = {
  title: "Datasets",
};

export default function DatasetsPage() {
  return (
    // Unauthenticated visitors go to /login?next=%2Fdatasets and return here.
    <AuthGuard redirectPath="/datasets">
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Datasets</h1>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                Saved price data you can reuse for backtests.
              </p>
            </div>
            <Link
              href="/backtest/new"
              className="inline-flex items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            >
              Upload price data
            </Link>
          </div>

          <div className="mt-8">
            <DatasetList />
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
