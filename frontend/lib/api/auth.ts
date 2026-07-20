/**
 * Authentication API functions (SPEC Section 25.1).
 *
 * These are the only API functions in this slice — Dataset and Backtest
 * clients arrive with their own tasks. Passwords are passed straight to the
 * request body and never logged, stored, or retained after the call.
 */

import { apiPostJson, apiRequest } from "./client";
import type {
  AuthenticatedUser,
  LoginRequest,
  RegisterRequest,
  RegisteredUser,
} from "./types";

export function registerUser(
  payload: RegisterRequest,
  options?: RequestInit,
): Promise<RegisteredUser> {
  return apiPostJson<RegisteredUser>("/api/auth/register", payload, options);
}

export function loginUser(
  payload: LoginRequest,
  options?: RequestInit,
): Promise<AuthenticatedUser> {
  return apiPostJson<AuthenticatedUser>("/api/auth/login", payload, options);
}

/** Returns 204 with no body; the backend clears the cookie. */
export function logoutUser(options?: RequestInit): Promise<void> {
  return apiRequest<void>("/api/auth/logout", { ...options, method: "POST" });
}

/** 401 UNAUTHENTICATED here means "no session", not an application failure. */
export function getCurrentUser(options?: RequestInit): Promise<AuthenticatedUser> {
  return apiRequest<AuthenticatedUser>("/api/auth/me", {
    ...options,
    method: "GET",
  });
}
