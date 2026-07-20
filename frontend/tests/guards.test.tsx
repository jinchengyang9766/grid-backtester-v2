import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGuard, GuestGuard } from "@/components/auth/auth-guard";
import { AppHeader } from "@/components/layout/app-header";
import { AuthProvider } from "@/lib/auth/auth-context";
import { isSafeNextPath, loginPathFor, resolveNextPath } from "@/lib/routing/next-path";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

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
  replace.mockClear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("next-path safety", () => {
  it.each(["/app", "/app/nested", "/datasets"])("accepts in-app path %s", (path) => {
    expect(isSafeNextPath(path)).toBe(true);
    expect(resolveNextPath(path)).toBe(path);
  });

  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/app/../../etc",
    "app",
    "",
    null,
    undefined,
  ])("rejects unsafe target %s", (path) => {
    expect(isSafeNextPath(path)).toBe(false);
    expect(resolveNextPath(path)).toBe("/history");
  });

  it("builds a login path carrying the original location", () => {
    expect(loginPathFor("/app")).toBe("/login?next=%2Fapp");
    expect(loginPathFor("/login")).toBe("/login");
    expect(loginPathFor("https://evil.example")).toBe("/login");
  });
});

describe("AuthGuard", () => {
  it("shows a loading state and does not redirect before auth resolves", async () => {
    fetchMock.mockReturnValue(new Promise<Response>(() => {}));
    render(
      <AuthProvider>
        <AuthGuard redirectPath="/app">
          <p>protected</p>
        </AuthGuard>
      </AuthProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Checking your session…");
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("renders protected content for an authenticated user", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    render(
      <AuthProvider>
        <AuthGuard redirectPath="/app">
          <p>protected</p>
        </AuthGuard>
      </AuthProvider>,
    );

    expect(await screen.findByText("protected")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects an unauthenticated visitor to /login with a next target", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    render(
      <AuthProvider>
        <AuthGuard redirectPath="/app">
          <p>protected</p>
        </AuthGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fapp"));
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });

  it("exposes a retry control when the auth check fails", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(
      <AuthProvider>
        <AuthGuard redirectPath="/app">
          <p>protected</p>
        </AuthGuard>
      </AuthProvider>,
    );

    const retry = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your account");
    expect(replace).not.toHaveBeenCalled();

    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    await userEvent.click(retry);
    expect(await screen.findByText("protected")).toBeInTheDocument();
  });
});

describe("GuestGuard", () => {
  it("renders the form for an unauthenticated visitor", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    render(
      <AuthProvider>
        <GuestGuard>
          <p>sign-in form</p>
        </GuestGuard>
      </AuthProvider>,
    );

    expect(await screen.findByText("sign-in form")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects an authenticated visitor away from the form", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    render(
      <AuthProvider>
        <GuestGuard>
          <p>sign-in form</p>
        </GuestGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/history"));
    expect(screen.queryByText("sign-in form")).not.toBeInTheDocument();
  });

  it("honours a safe next target when redirecting", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "a@b.c" }));
    render(
      <AuthProvider>
        <GuestGuard nextPath="/app/somewhere">
          <p>sign-in form</p>
        </GuestGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/somewhere"));
  });

  it("does not redirect before auth resolves", async () => {
    fetchMock.mockReturnValue(new Promise<Response>(() => {}));
    render(
      <AuthProvider>
        <GuestGuard>
          <p>sign-in form</p>
        </GuestGuard>
      </AuthProvider>,
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("still shows the form when the auth check errored", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(
      <AuthProvider>
        <GuestGuard>
          <p>sign-in form</p>
        </GuestGuard>
      </AuthProvider>,
    );

    // A failed /me must never lock the user out of signing in.
    expect(await screen.findByText("sign-in form")).toBeInTheDocument();
  });
});

describe("app header", () => {
  it("shows the signed-in email and a logout control", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "shell@b.c" }));
    render(
      <AuthProvider>
        <AppHeader />
      </AuthProvider>,
    );

    expect(await screen.findByText("shell@b.c")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("signs out and returns to the login page", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "shell@b.c" }));
    render(
      <AuthProvider>
        <AppHeader />
      </AuthProvider>,
    );
    await screen.findByText("shell@b.c");

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("prevents repeated logout clicks and reports failure safely", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "shell@b.c" }));
    render(
      <AuthProvider>
        <AppHeader />
      </AuthProvider>,
    );
    await screen.findByText("shell@b.c");

    let resolveLogout: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveLogout = r)));

    const button = screen.getByRole("button", { name: /sign out|signing out/i });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);

    const logoutCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).endsWith("/api/auth/logout"),
    );
    expect(logoutCalls).toHaveLength(1);

    resolveLogout?.(new Response(null, { status: 204 }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
