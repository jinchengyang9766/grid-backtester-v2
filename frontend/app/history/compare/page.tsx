import type { Metadata } from "next";

import { AuthGuard } from "@/components/auth/auth-guard";
import { CompareResults } from "@/components/backtests/compare-results";
import { AppHeader } from "@/components/layout/app-header";

export const metadata: Metadata = {
  title: "Compare backtests",
};

/** Positive, distinct integers only; anything else is dropped. */
function parseIds(raw: string | string[] | undefined): number[] {
  const text = Array.isArray(raw) ? raw[0] : raw;
  if (!text) return [];
  const ids: number[] = [];
  for (const part of text.split(",")) {
    const trimmed = part.trim();
    if (!/^\d+$/.test(trimmed)) continue;
    const value = Number(trimmed);
    if (Number.isSafeInteger(value) && value > 0 && !ids.includes(value)) ids.push(value);
  }
  return ids;
}

export default async function CompareBacktestsPage({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string | string[] }>;
}) {
  const { ids: raw } = await searchParams;
  const ids = parseIds(raw);

  return (
    <AuthGuard
      redirectPath={ids.length > 0 ? `/history/compare?ids=${ids.join(",")}` : "/history/compare"}
    >
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">Compare backtests</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Stored metrics side by side. Only backtest identifiers appear in
            this page&apos;s address.
          </p>
          <div className="mt-8">
            <CompareResults ids={ids} />
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
