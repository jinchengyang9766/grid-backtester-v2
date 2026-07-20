"use client";

import { useAuthContext, type AuthContextValue } from "./auth-context";

/** Access the current authentication state and its login/logout actions. */
export function useAuth(): AuthContextValue {
  return useAuthContext();
}
