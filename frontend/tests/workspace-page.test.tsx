import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppLayout from "@/app/app/layout";
import WorkspacePage from "@/app/app/page";
import LandingPage from "@/app/page";
import { AuthProvider } from "@/lib/auth/auth-context";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/app",
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

/** The layout is a server component wrapper, safe to call directly here. */
function renderWorkspace() {
  return render(
    <AuthProvider>
      {AppLayout({ children: <WorkspacePage /> })}
    </AuthProvider>,
  );
}

describe("workspace page", () => {
  it("shows the signed-in email and a ready message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    // Shown twice on purpose: in the header and in the ready message.
    expect(screen.getAllByText("owner@example.com")).toHaveLength(2);
    expect(screen.getByText(/signed in as/i)).toBeInTheDocument();
    expect(screen.getByText(/your workspace is ready/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("links to implemented sections and marks unbuilt ones unavailable", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    renderWorkspace();
    await screen.findByRole("heading", { name: "Workspace" });

    // Implemented in Task 21, so these are now real links.
    expect(screen.getByRole("link", { name: /Datasets/ })).toHaveAttribute(
      "href",
      "/datasets",
    );
    expect(screen.getByRole("link", { name: /New Backtest/ })).toHaveAttribute(
      "href",
      "/backtest/new",
    );

    // History still has no page, so it must not be a navigable link.
    expect(screen.getByText("Backtest History")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Backtest History/ }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Not available yet")).toHaveLength(1);
  });

  it("shows no invented dataset or backtest figures", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    const { container } = renderWorkspace();
    await screen.findByRole("heading", { name: "Workspace" });

    // Only the real session email; no fabricated counts, returns, or equity.
    expect(container.textContent).not.toMatch(/\d+\s*(datasets?|backtests?|runs?)\b/i);
    expect(container.textContent).not.toMatch(/%|equity|sharpe|drawdown/i);
  });

  it("redirects an unauthenticated visitor to login with a next target", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    renderWorkspace();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fapp"));
    expect(screen.queryByRole("heading", { name: "Workspace" })).not.toBeInTheDocument();
  });

  it("uses a single top-level heading", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    renderWorkspace();
    await screen.findByRole("heading", { name: "Workspace" });

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("landing page", () => {
  it("is public and never redirects", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
    render(
      <AuthProvider>
        <LandingPage />
      </AuthProvider>,
    );

    expect(await screen.findByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers the workspace to a signed-in visitor without redirecting", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    render(
      <AuthProvider>
        <LandingPage />
      </AuthProvider>,
    );

    expect(await screen.findByRole("link", { name: "Open workspace" })).toHaveAttribute(
      "href",
      "/app",
    );
    expect(screen.getByText(/signed in as owner@example.com/i)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
