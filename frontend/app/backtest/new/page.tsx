import type { Metadata } from "next";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppHeader } from "@/components/layout/app-header";
import { DatasetUploadWizard } from "@/components/upload/dataset-upload-wizard";
import { ExistingDatasetHandoff } from "@/components/upload/existing-dataset-handoff";

export const metadata: Metadata = {
  title: "New backtest",
};

/** Only a positive integer id is accepted from the query string. */
function parseDatasetId(value: string | string[] | undefined): number | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (raw === undefined || !/^\d+$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export default async function NewBacktestPage({
  searchParams,
}: {
  searchParams: Promise<{ dataset_id?: string | string[] }>;
}) {
  const { dataset_id: datasetIdParam } = await searchParams;
  const datasetId = parseDatasetId(datasetIdParam);

  return (
    <AuthGuard redirectPath="/backtest/new">
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">New backtest</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Import price data, then configure a strategy.
          </p>

          <div className="mt-8">
            {datasetId === null ? (
              <DatasetUploadWizard />
            ) : (
              <ExistingDatasetHandoff datasetId={datasetId} />
            )}
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
