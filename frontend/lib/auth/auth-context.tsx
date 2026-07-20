"use client";

/**
 * Client-side authentication state.
 *
 * The HttpOnly cookie is the sole source of truth for the session: this
 * provider only mirrors what `GET /api/auth/me` reports. Nothing is written to
 * localStorage or sessionStorage, and no JWT is ever read or decoded — a
 * cached "logged in" flag could disagree with the cookie and produce a UI that
 * claims a session the server will reject.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getCurrentUser, loginUser, logoutUser } from "@/lib/api/auth";
import { ApiClientError } from "@/lib/api/errors";
import type { AuthenticatedUser, LoginRequest } from "@/lib/api/types";

export type AuthState =
  | { status: "loading"; user: null }
  | { status: "authenticated"; user: AuthenticatedUser }
  | { status: "unauthenticated"; user: null }
  | { status: "error"; user: null; message: string };

export interface AuthContextValue {
  state: AuthState;
  user: AuthenticatedUser | null;
  login: (payload: LoginRequest) => Promise<AuthenticatedUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const LOADING: AuthState = { status: "loading", user: null };
const UNAUTHENTICATED: AuthState = { status: "unauthenticated", user: null };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const existing = useContext(AuthContext);
  const [state, setState] = useState<AuthState>(LOADING);

  // Monotonic request id: only the newest in-flight /me may publish a result,
  // so a slow refresh can never overwrite a newer login or logout.
  const generation = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const publish = useCallback((next: AuthState, forGeneration: number) => {
    if (!mounted.current) return;
    if (forGeneration !== generation.current) return;
    setState(next);
  }, []);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const current = ++generation.current;
      publish(LOADING, current);
      try {
        const user = await getCurrentUser({ signal });
        publish({ status: "authenticated", user }, current);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiClientError && error.isUnauthenticated) {
          // A missing session is a normal state, not a visible error.
          publish(UNAUTHENTICATED, current);
          return;
        }
        const message =
          error instanceof ApiClientError
            ? error.message
            : "Could not load your account.";
        publish({ status: "error", user: null, message }, current);
      }
    },
    [publish],
  );

  // One /me on mount. A nested provider reuses the outer context instead of
  // issuing a duplicate request.
  useEffect(() => {
    if (existing) return;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [existing, refresh]);

  const login = useCallback(
    async (payload: LoginRequest) => {
      const user = await loginUser(payload);
      // Claim the newest generation so any in-flight /me is discarded.
      const current = ++generation.current;
      publish({ status: "authenticated", user }, current);
      return user;
    },
    [publish],
  );

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } finally {
      const current = ++generation.current;
      publish(UNAUTHENTICATED, current);
    }
  }, [publish]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      user: state.status === "authenticated" ? state.user : null,
      login,
      logout,
      refresh: () => refresh(),
    }),
    [state, login, logout, refresh],
  );

  // Nested providers must not start a second session: reuse the outer value.
  if (existing) {
    return <AuthContext.Provider value={existing}>{children}</AuthContext.Provider>;
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return value;
}
