"use client";

import Link from "next/link";
import { useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { registerUser } from "@/lib/api/auth";
import { ApiClientError, fieldErrorsFrom } from "@/lib/api/errors";

/** The backend's only password rule (SPEC Section 24.2) — no complexity rules. */
export const MINIMUM_PASSWORD_LENGTH = 8;

export function RegisterForm() {
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    setFormError(null);
    setFieldErrors({});

    const nextFieldErrors: Record<string, string> = {};
    if (!email.trim()) nextFieldErrors.email = "Enter your email address.";
    if (password.length < MINIMUM_PASSWORD_LENGTH) {
      nextFieldErrors.password = `Password must be at least ${MINIMUM_PASSWORD_LENGTH} characters.`;
    }
    if (confirmPassword !== password) {
      nextFieldErrors.confirmPassword = "Passwords do not match.";
    }
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setPending(true);
    try {
      // Only email and password are sent; the confirmation never leaves here.
      const user = await registerUser({ email: email.trim(), password });
      setPassword("");
      setConfirmPassword("");
      // Registration does not create a session — the user still signs in.
      setRegisteredEmail(user.email);
    } catch (error) {
      setPassword("");
      setConfirmPassword("");
      if (error instanceof ApiClientError) {
        const fields = fieldErrorsFrom(error);
        if (Object.keys(fields).length > 0) setFieldErrors(fields);
        setFormError(error.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setPending(false);
    }
  }

  if (registeredEmail !== null) {
    return (
      <div className="space-y-5">
        <Alert tone="success" title="Account created">
          <p>
            {registeredEmail} is registered. Sign in to continue.
          </p>
        </Alert>
        <Link
          href="/login"
          className="inline-flex w-full items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        >
          Go to sign in
        </Link>
      </div>
    );
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

      <FormField
        id={passwordId}
        label="Password"
        description={`At least ${MINIMUM_PASSWORD_LENGTH} characters.`}
        error={fieldErrors.password}
      >
        {(aria) => (
          <Input
            {...aria}
            type="password"
            name="password"
            autoComplete="new-password"
            required
            value={password}
            invalid={Boolean(fieldErrors.password)}
            onChange={(event) => setPassword(event.target.value)}
          />
        )}
      </FormField>

      <FormField
        id={confirmId}
        label="Confirm password"
        error={fieldErrors.confirmPassword}
      >
        {(aria) => (
          <Input
            {...aria}
            type="password"
            name="confirmPassword"
            autoComplete="new-password"
            required
            value={confirmPassword}
            invalid={Boolean(fieldErrors.confirmPassword)}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        )}
      </FormField>

      <Button
        type="submit"
        pending={pending}
        pendingLabel="Creating account…"
        className="w-full"
      >
        Create account
      </Button>

      <p className="text-sm text-slate-600 dark:text-slate-400">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 dark:text-sky-400"
        >
          Sign in
        </Link>
      </p>
    </form>
  );
}
