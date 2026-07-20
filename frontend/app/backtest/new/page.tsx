import type { Metadata } from "next";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppHeader } from "@/components/layout/app-header";
import { BacktestRoute } from "@/components/backtests/backtest-route";

export const metadata: Metadata = {
  title: "New backtest",
};

/** Only a positive integer id is accepted from the query string. */
function parseId(value: string | string[] | undefined): number | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (raw === undefined || !/^\d+$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export default async function NewBacktestPage({
  searchParams,
}: {
  searchParams: Promise<{
    dataset_id?: string | string[];
    backtest_id?: string | string[];
    configure?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const datasetId = parseId(params.dataset_id);
  const backtestId = parseId(params.backtest_id);
  const configure =
    (Array.isArray(params.configure) ? params.configure[0] : params.configure) === "1";

  return (
    <AuthGuard redirectPath="/backtest/new">
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main id="main-content" className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">New backtest</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Import price data, configure a strategy, and run it.
          </p>

          <div className="mt-8">
            <BacktestRoute
              datasetId={datasetId}
              backtestId={backtestId}
              startAtConfiguration={configure}
            />
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
