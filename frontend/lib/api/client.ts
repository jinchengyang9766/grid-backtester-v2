/**
 * The single fetch wrapper every API call goes through.
 *
 * Requests always target same-origin `/api/...` paths, which the route
 * handler at `app/api/[...path]/route.ts` forwards to the backend. That keeps
 * the session cookie same-origin (SPEC Section 24.5) so the browser attaches
 * it automatically: this module never reads, writes, decodes, or stores the
 * access token, and never builds an Authorization header.
 */

import {
  ApiClientError,
  isApiErrorEnvelope,
  GENERIC_SERVER_MESSAGE,
} from "./errors";

/** Only paths inside the backend's own namespace may be requested. */
const API_PREFIX = "/api/";

function assertRelativeApiPath(path: string): void {
  if (!path.startsWith(API_PREFIX)) {
    throw new TypeError(
      `apiRequest path must be a relative "${API_PREFIX}" path; received "${path}"`,
    );
  }
  // "//host" and "/api/../.." would escape the intended origin or namespace.
  if (path.startsWith("//") || path.includes("..")) {
    throw new TypeError(`apiRequest path is not a safe relative path: "${path}"`);
  }
}

function isJsonContentType(response: Response): boolean {
  const contentType = response.headers.get("content-type");
  return contentType !== null && contentType.toLowerCase().includes("json");
}

/**
 * Parse a body only when the server says it is JSON. A 500 that returns an
 * HTML error page must never be surfaced as text to the user.
 */
async function readJson(response: Response): Promise<unknown> {
  if (!isJsonContentType(response)) return undefined;
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

/**
 * Perform one API request. Never retries — a failed POST is reported to the
 * caller rather than silently repeated, which would risk duplicate writes.
 *
 * @throws {ApiClientError} for any non-2xx response or transport failure.
 *   `AbortError` is re-thrown unchanged so callers can tell a cancelled
 *   request from a real failure.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  assertRelativeApiPath(path);

  let response: Response;
  try {
    response = await fetch(path, {
      // Same-origin: enough for the HttpOnly cookie, and never sends it
      // anywhere else.
      credentials: "same-origin",
      ...options,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw ApiClientError.network(cause);
  }

  if (response.status === 204) return undefined as T;

  const body = await readJson(response);

  if (!response.ok) {
    if (isApiErrorEnvelope(body)) {
      throw new ApiClientError(
        response.status,
        body.error.code,
        body.error.message,
        body.error.details,
      );
    }
    // Non-enveloped failure: report a safe generic message, never raw output.
    throw ApiClientError.unexpected(response.status);
  }

  return body as T;
}

/** POST a JSON document and decode the JSON response. */
export function apiPostJson<T>(
  path: string,
  payload: unknown,
  options: RequestInit = {},
): Promise<T> {
  return apiRequest<T>(path, {
    ...options,
    method: "POST",
    headers: { "Content-Type": "application/json", ...options.headers },
    body: JSON.stringify(payload),
  });
}

export { ApiClientError, GENERIC_SERVER_MESSAGE };
