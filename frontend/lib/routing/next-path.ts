/**
 * Safe handling of SPEC Section 27's `/login?next=<original path>` parameter.
 *
 * Only same-origin relative paths are honoured. An attacker-supplied absolute
 * URL, protocol-relative `//evil.example`, or backslash variant would turn the
 * login redirect into an open redirect, so anything that is not a plain
 * in-app path falls back to the default destination.
 */

export const NEXT_PARAM = "next";

/**
 * Where an authenticated user lands when no explicit target is given.
 * SPEC Section 27 places this at /history, which now exists.
 */
export const DEFAULT_AUTHENTICATED_PATH = "/history";

export function isSafeNextPath(value: string | null | undefined): value is string {
  if (!value) return false;
  if (!value.startsWith("/")) return false;
  // "//host" and "/\host" are both browser-recognised protocol-relative URLs.
  if (value.startsWith("//") || value.startsWith("/\\")) return false;
  if (value.includes("..")) return false;
  return true;
}

/** The validated `next` target, or the default authenticated destination. */
export function resolveNextPath(value: string | null | undefined): string {
  return isSafeNextPath(value) ? value : DEFAULT_AUTHENTICATED_PATH;
}

/** Build the login URL a guard should send an unauthenticated visitor to. */
export function loginPathFor(currentPath: string): string {
  if (!isSafeNextPath(currentPath) || currentPath === "/login") return "/login";
  return `/login?${NEXT_PARAM}=${encodeURIComponent(currentPath)}`;
}
