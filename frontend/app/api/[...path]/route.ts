/**
 * Same-origin backend proxy (SPEC Section 24.5, "Preferred: same-origin via a
 * Next.js /api proxy").
 *
 * The browser only ever talks to the Next.js origin, so the access-token
 * cookie stays same-origin with `SameSite=Lax` and no credentialed CORS is
 * needed. This handler relays each request to the configured backend and
 * returns the response essentially unchanged:
 *
 *     browser  /api/auth/login  ->  Next.js  ->  BACKEND_ORIGIN/api/auth/login
 *
 * The body is streamed through untouched, so JSON, multipart uploads, and the
 * binary CSV/PDF exports all pass without being parsed, decoded, or buffered.
 */

import { NextResponse, type NextRequest } from "next/server";

/** Server-only: never `NEXT_PUBLIC_`, so the backend origin is never shipped. */
const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:8000";

/** Only this backend namespace may be reached; the proxy is not general. */
const ALLOWED_PREFIX = "api";

/**
 * Hop-by-hop and transport headers that belong to the browser→Next.js
 * connection and must not be replayed onto the Next.js→backend one.
 */
const STRIPPED_REQUEST_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

const STRIPPED_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "content-encoding",
  "content-length",
]);

function backendOrigin(): string {
  return process.env.BACKEND_ORIGIN ?? DEFAULT_BACKEND_ORIGIN;
}

function jsonError(status: number, code: string, message: string): NextResponse {
  return NextResponse.json({ error: { code, message } }, { status });
}

/**
 * Join the captured segments into a backend path.
 *
 * The route file lives at `app/api/[...path]`, so `segments` holds only what
 * follows `/api` — `/api/auth/me` arrives as `["auth", "me"]`. The `/api`
 * prefix is therefore re-added here as a constant, which is what keeps this
 * from being a general-purpose open proxy: no request can reach any other
 * backend namespace, whatever the segments contain.
 */
function resolveBackendUrl(segments: string[], search: string): URL | null {
  if (segments.length === 0) return null;
  if (segments.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return null;
  }

  const origin = backendOrigin();
  // Each segment is encoded so a crafted value cannot inject "?", "#", or a
  // second path root into the constructed URL.
  const path = segments.map(encodeURIComponent).join("/");
  const target = new URL(`${origin.replace(/\/$/, "")}/${ALLOWED_PREFIX}/${path}${search}`);

  // Belt and braces: the result must still be the configured backend origin.
  if (target.origin !== new URL(origin).origin) return null;
  return target;
}

function forwardRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!STRIPPED_REQUEST_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  return headers;
}

function forwardResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    if (!STRIPPED_RESPONSE_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });

  // Several Set-Cookie headers must survive as separate headers rather than
  // being folded into one comma-joined value.
  const setCookie = response.headers.getSetCookie?.();
  if (setCookie && setCookie.length > 0) {
    headers.delete("set-cookie");
    for (const cookie of setCookie) headers.append("set-cookie", cookie);
  }
  return headers;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const target = resolveBackendUrl(path, request.nextUrl.search);
  if (target === null) {
    return jsonError(404, "NOT_FOUND", "Not found.");
  }

  const method = request.method;
  const hasBody = method !== "GET" && method !== "HEAD";

  // Only multipart uploads are streamed.
  //
  // Streaming is what keeps a multipart boundary byte-exact and lets an upload
  // exceed available memory, so it is worth keeping for the one place that
  // needs it. Everywhere else it is actively harmful: when the backend answers
  // 401, undici prepares to replay the request with credentials, and a request
  // whose body is a stream has already been consumed and cannot be replayed.
  // It raises "expected non-null body source", the real 401 is discarded, and
  // the user is told the server is unavailable when in fact their session had
  // simply expired. JSON API bodies are small, so buffering them costs nothing
  // and makes every 401 arrive intact.
  const contentType = request.headers.get("content-type") ?? "";
  const streamBody = hasBody && contentType.toLowerCase().startsWith("multipart/");
  const body = hasBody ? (streamBody ? request.body : await request.arrayBuffer()) : undefined;

  let backendResponse: Response;
  try {
    backendResponse = await fetch(target, {
      method,
      headers: forwardRequestHeaders(request),
      body,
      // Required by undici whenever a stream is used as the request body.
      ...(streamBody ? { duplex: "half" } : {}),
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    } as RequestInit);
  } catch {
    // A navigation away, or any other client-side abort, tears down this
    // request too. That is not a backend outage, and reporting it as one puts
    // a false "the server is unavailable" in front of a user who simply
    // clicked something else. The client is already gone, so 499 is never
    // rendered — it exists so the mistaken 502 cannot be.
    if (request.signal.aborted) {
      return jsonError(499, "REQUEST_ABORTED", "The request was cancelled.");
    }
    // Never leak the backend origin or a stack trace to the browser.
    return jsonError(
      502,
      "BACKEND_UNAVAILABLE",
      "The application server is unavailable. Please try again.",
    );
  }

  // Body is relayed as a stream, so binary exports are never text-converted.
  return new Response(backendResponse.body, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers: forwardResponseHeaders(backendResponse),
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;

/** Proxied responses depend on the request cookie and must never be cached. */
export const dynamic = "force-dynamic";
