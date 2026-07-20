import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/lib/auth/auth-context";
import { useAuth } from "@/lib/auth/use-auth";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const UNAUTHENTICATED_BODY = {
  error: { code: "UNAUTHENTICATED", message: "Authentication required." },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

/** Surfaces provider state and actions for assertions. */
function Probe() {
  const { state, user, login, logout, refresh } = useAuth();
  return (
    <div>
      <p data-testid="status">{state.status}</p>
      <p data-testid="email">{user?.email ?? "none"}</p>
      <p data-testid="message">
        {state.status === "error" ? state.message : ""}
      </p>
      <button
        onClick={() => {
          void login({ email: "a@b.c", password: "secret123" }).catch(() => undefined);
        }}
      >
        do-login
      </button>
      {/* logout() clears state but still rejects so callers can report it. */}
      <button onClick={() => void logout().catch(() => undefined)}>do-logout</button>
      <button onClick={() => void refresh()}>do-refresh</button>
    </div>
  );
}

function renderProvider(children = <Probe />) {
  return render(<AuthProvider>{children}</AuthProvider>);
}

function meCalls(): number {
  return fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/auth/me")).length;
}

describe("initial session resolution", () => {
  it("starts in the loading state", async () => {
    let resolve: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    renderProvider();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await act(async () => {
      resolve?.(jsonResponse({ id: 1, email: "a@b.c" }));
    });
  });

  it("becomes authenticated when /me returns a user", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("email")).toHaveTextContent("a@b.c");
  });

  it("treats 401 UNAUTHENTICATED as a normal signed-out state, not an error", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(screen.getByTestId("message")).toHaveTextContent("");
  });

  it("becomes an error state on 500", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>oops</html>", { status: 500, headers: { "content-type": "text/html" } }),
    );
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
    expect(screen.getByTestId("message").textContent).not.toContain("<html>");
  });

  it("becomes an error state on network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
  });

  it("issues exactly one /me request on mount", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(meCalls()).toBe(1);
  });

  it("does not issue a second /me when providers are nested", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    render(
      <AuthProvider>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(meCalls()).toBe(1);
  });
});

describe("actions", () => {
  it("retries via refresh after an error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));

    fetchMock.mockResolvedValue(jsonResponse({ id: 7, email: "retry@b.c" }));
    await userEvent.click(screen.getByRole("button", { name: "do-refresh" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("email")).toHaveTextContent("retry@b.c");
  });

  it("login updates the user without decoding any token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(UNAUTHENTICATED_BODY, 401));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 2, email: "in@b.c" }));
    await userEvent.click(screen.getByRole("button", { name: "do-login" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("email")).toHaveTextContent("in@b.c");
  });

  it("logout clears the user", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await userEvent.click(screen.getByRole("button", { name: "do-logout" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(screen.getByTestId("email")).toHaveTextContent("none");
  });

  it("clears the user even when the logout request fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await userEvent.click(screen.getByRole("button", { name: "do-logout" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
  });

  it("registration does not authenticate the session", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    const { registerUser } = await import("@/lib/api/auth");
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: 3, email: "new@b.c", created_at: "2026-01-01T00:00:00Z" }, 201),
    );
    await act(async () => {
      await registerUser({ email: "new@b.c", password: "secret123" });
    });
    // Still signed out: only an explicit login creates a session.
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    expect(screen.getByTestId("email")).toHaveTextContent("none");
  });
});

describe("concurrency", () => {
  it("a slow /me does not overwrite a newer login result", async () => {
    let resolveMe: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveMe = r)));
    renderProvider();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");

    // Login resolves first, while /me is still pending.
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 9, email: "fresh@b.c" }));
    await userEvent.click(screen.getByRole("button", { name: "do-login" }));
    await waitFor(() => expect(screen.getByTestId("email")).toHaveTextContent("fresh@b.c"));

    // The stale /me now returns a different (older) user and must be ignored.
    await act(async () => {
      resolveMe?.(jsonResponse({ id: 1, email: "stale@b.c" }));
    });
    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("email")).toHaveTextContent("fresh@b.c");
  });

  it("a slow /me does not resurrect a session after logout", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    let resolveMe: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveMe = r)));
    await userEvent.click(screen.getByRole("button", { name: "do-refresh" }));

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await userEvent.click(screen.getByRole("button", { name: "do-logout" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    await act(async () => {
      resolveMe?.(jsonResponse({ id: 1, email: "a@b.c" }));
    });
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });

  it("aborts the in-flight /me on unmount without warning", async () => {
    const abortSpy = vi.fn();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            abortSpy();
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );
    const { unmount } = renderProvider();
    unmount();
    await waitFor(() => expect(abortSpy).toHaveBeenCalled());
  });
});

describe("storage", () => {
  it("never writes authentication data to local or session storage", async () => {
    const localSpy = vi.spyOn(Storage.prototype, "setItem");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 2, email: "in@b.c" }));
    await userEvent.click(screen.getByRole("button", { name: "do-login" }));
    await waitFor(() => expect(screen.getByTestId("email")).toHaveTextContent("in@b.c"));

    expect(localSpy).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
