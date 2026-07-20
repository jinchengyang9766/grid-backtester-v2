import type { Metadata } from "next";
import { Suspense } from "react";

import { GuestGuard } from "@/components/auth/auth-guard";
import { LoginForm } from "@/components/auth/login-form";
import { LoadingState } from "@/components/ui/loading-state";

export const metadata: Metadata = {
  title: "Sign in",
};

/** Reads `?next=` (SPEC Section 27), so it needs a Suspense boundary. */
function LoginPanel({ nextPath }: { nextPath?: string }) {
  return (
    <GuestGuard nextPath={nextPath}>
      <LoginForm />
    </GuestGuard>
  );
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const nextPath = Array.isArray(next) ? next[0] : next;

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Access your saved datasets and backtests.
      </p>
      <div className="mt-8">
        <Suspense fallback={<LoadingState label="Loading sign-in form…" />}>
          <LoginPanel nextPath={nextPath} />
        </Suspense>
      </div>
    </main>
  );
}
