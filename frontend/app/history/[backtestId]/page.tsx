import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppHeader } from "@/components/layout/app-header";
import { BacktestDetailPage } from "@/components/results/backtest-detail-page";

export const metadata: Metadata = {
  title: "Backtest result",
};

export default async function BacktestResultPage({
  params,
}: {
  params: Promise<{ backtestId: string }>;
}) {
  const { backtestId } = await params;
  if (!/^\d+$/.test(backtestId)) notFound();
  const id = Number(backtestId);
  if (!Number.isSafeInteger(id) || id <= 0) notFound();

  return (
    <AuthGuard redirectPath={`/history/${id}`}>
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          <BacktestDetailPage backtestId={id} />
        </main>
      </div>
    </AuthGuard>
  );
}
