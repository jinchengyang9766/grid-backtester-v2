"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { ApiClientError, fieldErrorsFrom } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/use-auth";
import { resolveNextPath } from "@/lib/routing/next-path";

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const emailId = useId();
  const passwordId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return; // never submit the same credentials twice

    setFormError(null);
    setFieldErrors({});

    const nextFieldErrors: Record<string, string> = {};
    if (!email.trim()) nextFieldErrors.email = "Enter your email address.";
    if (!password) nextFieldErrors.password = "Enter your password.";
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setPending(true);
    try {
      await login({ email: email.trim(), password });
      router.replace(resolveNextPath(searchParams.get("next")));
    } catch (error) {
      // Discard the rejected password rather than leaving it in the DOM.
      setPassword("");
      if (error instanceof ApiClientError) {
        const fields = fieldErrorsFrom(error);
        if (Object.keys(fields).length > 0) setFieldErrors(fields);
        // The backend's message is deliberately generic and never says which
        // credential was wrong; show it verbatim.
        setFormError(error.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      {formError && <Alert tone="error">{formError}</Alert>}

      <FormField id={emailId} label="Email" error={fieldErrors.email}>
        {(aria) => (
          <Input
            {...aria}
            type="email"
            name="email"
            autoComplete="email"
            autoFocus
            required
            value={email}
            invalid={Boolean(fieldErrors.email)}
            onChange={(event) => setEmail(event.target.value)}
          />
        )}
      </FormField>

      <FormField id={passwordId} label="Password" error={fieldErrors.password}>
        {(aria) => (
          <Input
            {...aria}
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            invalid={Boolean(fieldErrors.password)}
            onChange={(event) => setPassword(event.target.value)}
          />
        )}
      </FormField>

      <Button type="submit" pending={pending} pendingLabel="Signing in…" className="w-full">
        Sign in
      </Button>

      <p className="text-sm text-slate-600 dark:text-slate-400">
        Don&apos;t have an account?{" "}
        <Link
          href="/register"
          className="font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 dark:text-sky-400"
        >
          Create one
        </Link>
      </p>
    </form>
  );
}
