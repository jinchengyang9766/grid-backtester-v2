import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST, DELETE } from "@/app/api/[...path]/route";

const BACKEND = "http://127.0.0.1:9999";

let fetchMock: ReturnType<typeof vi.fn>;
const originalOrigin = process.env.BACKEND_ORIGIN;

beforeEach(() => {
  process.env.BACKEND_ORIGIN = BACKEND;
  fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  if (originalOrigin === undefined) delete process.env.BACKEND_ORIGIN;
  else process.env.BACKEND_ORIGIN = originalOrigin;
});

function params(...path: string[]) {
  return { params: Promise.resolve({ path }) };
}

function request(url: string, init?: RequestInit): NextRequest {
  return new NextRequest(new Request(url, init));
}

/** The URL the proxy forwarded to the backend. */
function forwardedUrl(): string {
  return String(fetchMock.mock.calls[0][0]);
}

function forwardedInit(): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

describe("request forwarding", () => {
  it("forwards path and method to the configured backend origin", async () => {
    await GET(request("http://localhost:3000/api/auth/me"), params("auth", "me"));
    expect(forwardedUrl()).toBe(`${BACKEND}/api/auth/me`);
    expect(forwardedInit().method).toBe("GET");
  });

  it("preserves the query string", async () => {
    await GET(
      request("http://localhost:3000/api/backtests?limit=20&offset=40&search=a%20b"),
      params("backtests"),
    );
    expect(forwardedUrl()).toBe(`${BACKEND}/api/backtests?limit=20&offset=40&search=a%20b`);
  });

  it("forwards the JSON body and content type", async () => {
    await POST(
      request("http://localhost:3000/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: "a@b.c", password: "secret123" }),
      }),
      params("auth", "login"),
    );
    const init = forwardedInit();
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(init.body).toBeDefined();
  });

  it("forwards the Cookie request header so the session reaches the backend", async () => {
    await GET(
      request("http://localhost:3000/api/auth/me", {
        headers: { cookie: "access_token=opaque-value" },
      }),
      params("auth", "me"),
    );
    expect(new Headers(forwardedInit().headers).get("cookie")).toBe("access_token=opaque-value");
  });

  it("strips hop-by-hop and host headers", async () => {
    await GET(
      request("http://localhost:3000/api/auth/me", {
        headers: { connection: "keep-alive", host: "localhost:3000" },
      }),
      params("auth", "me"),
    );
    const headers = new Headers(forwardedInit().headers);
    expect(headers.has("connection")).toBe(false);
    expect(headers.has("host")).toBe(false);
  });

  it("passes a multipart body through without decoding it", async () => {
    const form = new FormData();
    form.append("file", new Blob(["date,close\n2024-01-01,1.00\n"]), "prices.csv");
    const incoming = request("http://localhost:3000/api/datasets/preview", {
      method: "POST",
      body: form,
    });
    const boundary = incoming.headers.get("content-type");

    await POST(incoming, params("datasets", "preview"));

    // The exact multipart boundary must survive, or the backend cannot parse it.
    expect(new Headers(forwardedInit().headers).get("content-type")).toBe(boundary);
    expect(boundary).toContain("multipart/form-data; boundary=");
  });
});

describe("response forwarding", () => {
  it("preserves status and content type", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "UNAUTHENTICATED", message: "x" } }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const response = await GET(
      request("http://localhost:3000/api/auth/me"),
      params("auth", "me"),
    );
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toBe("application/json");
    expect(await response.json()).toEqual({
      error: { code: "UNAUTHENTICATED", message: "x" },
    });
  });

  it("relays a 204 with no body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const response = await POST(
      request("http://localhost:3000/api/auth/logout", { method: "POST" }),
      params("auth", "logout"),
    );
    expect(response.status).toBe(204);
  });

  it("preserves multiple Set-Cookie headers separately", async () => {
    const backendResponse = new Response(null, { status: 204 });
    backendResponse.headers.append("set-cookie", "access_token=a; Path=/api; HttpOnly");
    backendResponse.headers.append("set-cookie", "other=b; Path=/api");
    fetchMock.mockResolvedValue(backendResponse);

    const response = await POST(
      request("http://localhost:3000/api/auth/login", { method: "POST" }),
      params("auth", "login"),
    );
    const cookies = response.headers.getSetCookie();
    expect(cookies).toHaveLength(2);
    expect(cookies[0]).toContain("access_token=");
    expect(cookies[1]).toContain("other=");
  });

  it("relays binary bodies without text conversion", async () => {
    // A PDF signature plus a byte that is invalid UTF-8 if decoded.
    const bytes = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0xff, 0x00, 0x01]);
    fetchMock.mockResolvedValue(
      new Response(bytes, {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'attachment; filename="backtest-1-report.pdf"',
        },
      }),
    );

    const response = await GET(
      request("http://localhost:3000/api/backtests/1/exports/report.pdf"),
      params("backtests", "1", "exports", "report.pdf"),
    );
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(response.headers.get("content-disposition")).toBe(
      'attachment; filename="backtest-1-report.pdf"',
    );
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
  });

  it("returns a safe envelope when the backend is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("ECONNREFUSED 127.0.0.1:9999"));
    const response = await GET(
      request("http://localhost:3000/api/auth/me"),
      params("auth", "me"),
    );
    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error.code).toBe("BACKEND_UNAVAILABLE");
    // The backend origin is never disclosed to the browser.
    expect(JSON.stringify(body)).not.toContain("127.0.0.1");
  });
});

describe("namespace restriction", () => {
  it.each([
    [["..", "internal"], "traversal segment"],
    [["auth", "..", "..", "internal"], "nested traversal"],
    [["", "auth"], "empty segment"],
    [[], "no segments"],
  ])("refuses %s (%s)", async (path) => {
    const response = await GET(
      request("http://localhost:3000/api/whatever"),
      params(...(path as string[])),
    );
    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("always forwards under the backend's /api namespace", async () => {
    // The prefix is a constant in the handler, so even an odd-looking
    // segment lands inside /api rather than at the backend root.
    await GET(request("http://localhost:3000/api/internal"), params("internal", "metrics"));
    expect(forwardedUrl()).toBe(`${BACKEND}/api/internal/metrics`);
  });

  it("cannot be redirected to another origin by a crafted segment", async () => {
    await DELETE(request("http://localhost:3000/api/x"), params("evil.example", "x"));
    // Encoded into a single path segment; the origin is untouched.
    expect(new URL(forwardedUrl()).origin).toBe(BACKEND);
    expect(forwardedUrl()).toBe(`${BACKEND}/api/evil.example/x`);
  });

  it("encodes a segment that would otherwise inject a query or fragment", async () => {
    await GET(request("http://localhost:3000/api/x"), params("auth", "me?admin=1"));
    expect(forwardedUrl()).toBe(`${BACKEND}/api/auth/me%3Fadmin%3D1`);
  });
});

describe("configuration", () => {
  it("reads the backend origin from a server-only environment variable", async () => {
    process.env.BACKEND_ORIGIN = "http://backend.internal:8123";
    await GET(request("http://localhost:3000/api/auth/me"), params("auth", "me"));
    expect(forwardedUrl()).toBe("http://backend.internal:8123/api/auth/me");
    // A NEXT_PUBLIC_ variable would be inlined into the browser bundle.
    expect(process.env.NEXT_PUBLIC_BACKEND_ORIGIN).toBeUndefined();
  });

  it("falls back to the documented local default", async () => {
    delete process.env.BACKEND_ORIGIN;
    await GET(request("http://localhost:3000/api/auth/me"), params("auth", "me"));
    expect(forwardedUrl()).toBe("http://127.0.0.1:8000/api/auth/me");
  });
});
