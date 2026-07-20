/**
 * Typed client-side model of the backend's standard error envelope
 * (SPEC Section 26):
 *
 *     { "error": { "code": "...", "message": "...", "details": { ... } } }
 *
 * Every failure the API client can produce — an enveloped backend error, an
 * unexpected non-JSON server response, or a transport failure — surfaces as
 * one `ApiClientError`, so callers never have to inspect raw responses.
 */

/** Codes the client itself synthesises when the backend did not supply one. */
export const NETWORK_ERROR_CODE = "NETWORK_ERROR";
export const UNEXPECTED_ERROR_CODE = "UNEXPECTED_ERROR";

/** Backend codes the UI branches on. */
export const UNAUTHENTICATED_CODE = "UNAUTHENTICATED";
export const INVALID_CREDENTIALS_CODE = "INVALID_CREDENTIALS";
export const EMAIL_ALREADY_REGISTERED_CODE = "EMAIL_ALREADY_REGISTERED";
export const VALIDATION_ERROR_CODE = "VALIDATION_ERROR";

/** Shown instead of any raw server output (HTML error pages, stack traces). */
export const GENERIC_SERVER_MESSAGE =
  "Something went wrong on the server. Please try again.";
export const GENERIC_NETWORK_MESSAGE =
  "Could not reach the server. Check your connection and try again.";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

/**
 * True only for the exact `{ error: { code, message } }` shape. Anything else
 * — an HTML error page, a bare string, a differently-shaped JSON body — is
 * treated as unexpected and never rendered verbatim to the user.
 */
export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const { error } = value as { error?: unknown };
  if (typeof error !== "object" || error === null) return false;
  const { code, message } = error as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string";
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** A transport failure: the request never produced an HTTP response. */
  static network(cause?: unknown): ApiClientError {
    const error = new ApiClientError(
      0,
      NETWORK_ERROR_CODE,
      GENERIC_NETWORK_MESSAGE,
    );
    if (cause !== undefined) error.cause = cause;
    return error;
  }

  /** A response the backend contract does not describe. */
  static unexpected(status: number): ApiClientError {
    return new ApiClientError(
      status,
      UNEXPECTED_ERROR_CODE,
      GENERIC_SERVER_MESSAGE,
    );
  }

  get isNetworkError(): boolean {
    return this.code === NETWORK_ERROR_CODE;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401 && this.code === UNAUTHENTICATED_CODE;
  }
}

/**
 * Field-level messages pulled out of a `VALIDATION_ERROR` envelope's
 * `details.errors[]`, keyed by the last segment of each `loc` path, so a form
 * can show the backend's own message under the offending input.
 */
export function fieldErrorsFrom(error: ApiClientError): Record<string, string> {
  const details = error.details;
  if (typeof details !== "object" || details === null) return {};
  const { errors } = details as { errors?: unknown };
  if (!Array.isArray(errors)) return {};

  const fields: Record<string, string> = {};
  for (const issue of errors) {
    if (typeof issue !== "object" || issue === null) continue;
    const { loc, message } = issue as { loc?: unknown; message?: unknown };
    if (!Array.isArray(loc) || typeof message !== "string") continue;
    const name = loc[loc.length - 1];
    // Ignore the leading "body"/"query" segment; key on the field itself.
    if (typeof name === "string" && name !== "body" && !(name in fields)) {
      fields[name] = message;
    }
  }
  return fields;
}
