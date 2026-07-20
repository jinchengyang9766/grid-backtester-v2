import type { Metadata } from "next";

import { GuestGuard } from "@/components/auth/auth-guard";
import { RegisterForm } from "@/components/auth/register-form";

export const metadata: Metadata = {
  title: "Create account",
};

export default function RegisterPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Create account</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Register to save datasets and backtest results.
      </p>
      <div className="mt-8">
        <GuestGuard>
          <RegisterForm />
        </GuestGuard>
      </div>
    </main>
  );
}
