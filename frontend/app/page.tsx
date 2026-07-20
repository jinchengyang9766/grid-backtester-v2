"use client";

/**
 * Public landing page (SPEC Section 27: `/`, auth not required).
 *
 * This route never redirects — it is a real landing page. Authentication
 * state only decides which call to action is shown, so there is no chance of
 * a redirect loop with `/login`.
 */

import Link from "next/link";

import { LoadingState } from "@/components/ui/loading-state";
import { useAuth } from "@/lib/auth/use-auth";

const LINK_PRIMARY =
  "inline-flex items-center justify-center rounded-md bg-sky-700 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600";
const LINK_SECONDARY =
  "inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700";

export default function LandingPage() {
  const { state } = useAuth();

  return (
    <main
      id="main-content"
      className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-16"
    >
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Grid Backtester
      </h1>
      <p className="mt-4 max-w-prose text-base text-slate-700 dark:text-slate-300">
        A research and educational tool for backtesting grid strategies on daily
        price data. Import a price series, configure a strategy, and review the
        result against two buy-and-hold benchmarks.
      </p>

      <div className="mt-8">
        {state.status === "loading" ? (
          <LoadingState label="Checking your session…" />
        ) : state.status === "authenticated" ? (
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/history" className={LINK_PRIMARY}>
              Open workspace
            </Link>
            <span className="text-sm text-slate-600 dark:text-slate-400">
              Signed in as {state.user.email}
            </span>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Link href="/login" className={LINK_PRIMARY}>
              Log in
            </Link>
            <Link href="/register" className={LINK_SECONDARY}>
              Register
            </Link>
          </div>
        )}
      </div>

      <p className="mt-12 max-w-prose text-xs text-slate-500 dark:text-slate-400">
        This tool is for research and education. It does not constitute
        investment advice. Past performance, whether real or simulated, does not
        guarantee future results.
      </p>
    </main>
  );
}
