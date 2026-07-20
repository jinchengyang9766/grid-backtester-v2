"use client";

/**
 * Route guards driven by authentication state.
 *
 * Both guards render a loading state until `/api/auth/me` resolves — a
 * redirect fired before that would bounce a signed-in user to the login page
 * on every refresh, because "not yet known" is not "not signed in".
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { useAuth } from "@/lib/auth/use-auth";
import { loginPathFor, resolveNextPath } from "@/lib/routing/next-path";

function AuthErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="mx-auto w-full max-w-md py-12">
      <Alert
        tone="error"
        title="Could not load your account"
        action={
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        }
      >
        {message}
      </Alert>
    </div>
  );
}

/** Wraps a protected page: unauthenticated visitors go to `/login?next=…`. */
export function AuthGuard({
  children,
  redirectPath,
}: {
  children: React.ReactNode;
  /** The path to return to after signing in (SPEC Section 27). */
  redirectPath: string;
}) {
  const { state, refresh } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (state.status === "unauthenticated") {
      router.replace(loginPathFor(redirectPath));
    }
  }, [state.status, router, redirectPath]);

  if (state.status === "loading") {
    return <LoadingState fullPage label="Checking your session…" />;
  }
  if (state.status === "error") {
    return <AuthErrorState message={state.message} onRetry={() => void refresh()} />;
  }
  if (state.status === "unauthenticated") {
    // Redirect already scheduled; render the same non-committal state.
    return <LoadingState fullPage label="Redirecting to sign in…" />;
  }
  return <>{children}</>;
}

/**
 * Wraps `/login` and `/register`: an already-authenticated visitor is sent on
 * to the app instead of being shown a sign-in form again.
 */
export function GuestGuard({
  children,
  nextPath,
}: {
  children: React.ReactNode;
  nextPath?: string | null;
}) {
  const { state } = useAuth();
  const router = useRouter();
  const destination = resolveNextPath(nextPath);

  useEffect(() => {
    if (state.status === "authenticated") {
      router.replace(destination);
    }
  }, [state.status, router, destination]);

  if (state.status === "loading") {
    return <LoadingState fullPage label="Checking your session…" />;
  }
  if (state.status === "authenticated") {
    return <LoadingState fullPage label="Redirecting…" />;
  }
  // An auth-check failure must not block sign-in: show the form anyway.
  return <>{children}</>;
}
