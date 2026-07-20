import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LegacyWorkspacePage from "@/app/app/page";
import LandingPage from "@/app/page";
import { AppNavigation } from "@/components/layout/app-navigation";
import { AuthProvider } from "@/lib/auth/auth-context";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/history",
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

describe("legacy /app route", () => {
  it("redirects to the history landing", async () => {
    render(<LegacyWorkspacePage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/history"));
  });

  it("shows a textual holding state rather than private content", () => {
    render(<LegacyWorkspacePage />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/backtest history/i);
    // Nothing private is rendered on the way through.
    expect(document.body.textContent).not.toMatch(/@example\.com/);
  });
});

describe("workspace navigation", () => {
  it("links every implemented section", () => {
    render(<AppNavigation />);
    expect(screen.getByRole("link", { name: /History/ })).toHaveAttribute(
      "href",
      "/history",
    );
    expect(screen.getByRole("link", { name: /Datasets/ })).toHaveAttribute(
      "href",
      "/datasets",
    );
    expect(screen.getByRole("link", { name: /New Backtest/ })).toHaveAttribute(
      "href",
      "/backtest/new",
    );
  });

  it("no longer advertises anything as unavailable", () => {
    render(<AppNavigation />);
    expect(screen.queryByText("Not available yet")).not.toBeInTheDocument();
    expect(screen.queryByText(/History not available/i)).not.toBeInTheDocument();
  });

  it("marks the current section in text, not colour alone", () => {
    render(<AppNavigation />);
    const current = screen.getByRole("link", { name: /History/ });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Current")).toBeInTheDocument();
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

    expect(await screen.findByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("sends a signed-in visitor to history without redirecting", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, email: "owner@example.com" }));
    render(
      <AuthProvider>
        <LandingPage />
      </AuthProvider>,
    );

    expect(await screen.findByRole("link", { name: "Open workspace" })).toHaveAttribute(
      "href",
      "/history",
    );
    expect(screen.getByText(/signed in as owner@example.com/i)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
