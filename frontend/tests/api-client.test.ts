import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiPostJson, apiRequest } from "@/lib/api/client";
import {
  ApiClientError,
  fieldErrorsFrom,
  GENERIC_NETWORK_MESSAGE,
  GENERIC_SERVER_MESSAGE,
  isApiErrorEnvelope,
} from "@/lib/api/errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("isApiErrorEnvelope", () => {
  it("accepts the standard envelope", () => {
    expect(isApiErrorEnvelope({ error: { code: "X", message: "m" } })).toBe(true);
  });

  it("rejects non-envelope values", () => {
    for (const value of [null, undefined, "text", 1, {}, { error: {} }, { error: null }]) {
      expect(isApiErrorEnvelope(value)).toBe(false);
    }
  });
});

describe("apiRequest success paths", () => {
  it("parses a JSON response", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    const result = await apiRequest<{ id: number; email: string }>("/api/auth/me");
    expect(result).toEqual({ id: 1, email: "a@b.c" });
  });

  it("returns undefined for 204 without parsing a body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiRequest<void>("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("does not parse a 200 body that is not JSON", async () => {
    fetchMock.mockResolvedValue(
      new Response("plain text", { status: 200, headers: { "content-type": "text/plain" } }),
    );
    await expect(apiRequest("/api/auth/me")).resolves.toBeUndefined();
  });

  it("sends the session cookie via same-origin credentials", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiRequest("/api/auth/me");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "same-origin" });
  });

  it("never builds an Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiPostJson("/api/auth/login", { email: "a@b.c", password: "secret123" });
    const headers = new Headers(
      (fetchMock.mock.calls[0][1] as RequestInit).headers as HeadersInit,
    );
    expect(headers.has("authorization")).toBe(false);
    expect(headers.get("content-type")).toBe("application/json");
  });
});

describe("apiRequest error paths", () => {
  it("throws ApiClientError from a standard envelope", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "INVALID_CREDENTIALS", message: "Incorrect email or password." } }, 401),
    );
    const error = await apiRequest("/api/auth/login").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiClientError);
    const apiError = error as ApiClientError;
    expect(apiError.status).toBe(401);
    expect(apiError.code).toBe("INVALID_CREDENTIALS");
    expect(apiError.message).toBe("Incorrect email or password.");
  });

  it("preserves validation details for field-level UI", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Request validation failed.",
            details: {
              errors: [
                { loc: ["body", "email"], message: "value is not a valid email address", type: "value_error" },
              ],
            },
          },
        },
        422,
      ),
    );
    const error = (await apiRequest("/api/auth/register").catch((e: unknown) => e)) as ApiClientError;
    expect(error.details).toBeDefined();
    expect(fieldErrorsFrom(error)).toEqual({ email: "value is not a valid email address" });
  });

  it("reports a safe generic error for a non-JSON server failure", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html><body>Internal Server Error stack trace</body></html>", {
        status: 500,
        headers: { "content-type": "text/html" },
      }),
    );
    const error = (await apiRequest("/api/auth/me").catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("UNEXPECTED_ERROR");
    expect(error.message).toBe(GENERIC_SERVER_MESSAGE);
    // The raw HTML never reaches the user-facing message.
    expect(error.message).not.toContain("stack trace");
    expect(error.message).not.toContain("<html>");
  });

  it("reports a distinguishable network error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = (await apiRequest("/api/auth/me").catch((e: unknown) => e)) as ApiClientError;
    expect(error.isNetworkError).toBe(true);
    expect(error.status).toBe(0);
    expect(error.message).toBe(GENERIC_NETWORK_MESSAGE);
  });

  it("flags 401 UNAUTHENTICATED distinctly from a server failure", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "UNAUTHENTICATED", message: "Authentication required." } }, 401),
    );
    const error = (await apiRequest("/api/auth/me").catch((e: unknown) => e)) as ApiClientError;
    expect(error.isUnauthenticated).toBe(true);
    expect(error.isNetworkError).toBe(false);
  });
});

describe("apiRequest safety rules", () => {
  it.each([
    "https://evil.example/api/auth/me",
    "//evil.example/api/auth/me",
    "/other/auth/me",
    "/api/../../etc/passwd",
  ])("rejects non-relative or escaping path %s", async (path) => {
    await expect(apiRequest(path)).rejects.toBeInstanceOf(TypeError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("propagates an AbortSignal and rethrows AbortError unchanged", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      expect(init.signal).toBe(controller.signal);
      return Promise.reject(new DOMException("Aborted", "AbortError"));
    });
    const error = await apiRequest("/api/auth/me", { signal: controller.signal }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(DOMException);
    expect((error as DOMException).name).toBe("AbortError");
  });

  it("never retries a failed POST", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "UNEXPECTED_ERROR", message: "boom" } }, 500),
    );
    await apiPostJson("/api/auth/login", { email: "a@b.c", password: "secret123" }).catch(
      () => undefined,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never retries a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await apiRequest("/api/auth/me").catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requests only relative same-origin paths", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiRequest("/api/auth/me");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/me");
  });
});
