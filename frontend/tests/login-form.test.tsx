import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { AuthProvider } from "@/lib/auth/auth-context";

const replace = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => searchParams,
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
  searchParams = new URLSearchParams();
  fetchMock = vi.fn().mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
  vi.stubGlobal("fetch", fetchMock);
});

async function renderForm() {
  render(
    <AuthProvider>
      <LoginForm />
    </AuthProvider>,
  );
  // Let the initial /me settle so the form is interactive.
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
}

function loginCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/auth/login"));
}

describe("fields and accessibility", () => {
  it("uses the correct input types and autocomplete hints", async () => {
    await renderForm();
    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("links to the registration page", async () => {
    await renderForm();
    expect(screen.getByRole("link", { name: "Create one" })).toHaveAttribute("href", "/register");
  });
});

describe("validation", () => {
  it("requires both fields and does not call the API", async () => {
    await renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(loginCalls()).toHaveLength(0);
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("submission", () => {
  it("signs in and navigates to the workspace", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app"));
    const [, init] = loginCalls()[0];
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      email: "a@b.c",
      password: "secret123",
    });
  });

  it("returns to a safe ?next= path after signing in", async () => {
    searchParams = new URLSearchParams("next=%2Fapp%2Fsomewhere");
    await renderForm();
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/somewhere"));
  });

  it("ignores an off-site ?next= target", async () => {
    searchParams = new URLSearchParams("next=https%3A%2F%2Fevil.example");
    await renderForm();
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app"));
  });

  it("submits with the Enter key", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: "a@b.c" }));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123{Enter}");

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app"));
  });

  it("shows the backend's generic message for invalid credentials", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "INVALID_CREDENTIALS", message: "Incorrect email or password." } },
        401,
      ),
    );

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect email or password.");
    // Never discloses which of the two credentials was wrong.
    expect(alert.textContent).not.toMatch(/email (is |was )?(not found|unknown)/i);
    expect(alert.textContent).not.toMatch(/password is (wrong|incorrect)/i);
    expect(replace).not.toHaveBeenCalled();
  });

  it("clears the password after a failed attempt", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "INVALID_CREDENTIALS", message: "Incorrect email or password." } },
        401,
      ),
    );

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    // The email is kept so the user need not retype it.
    expect(screen.getByLabelText("Email")).toHaveValue("a@b.c");
  });

  it("shows a retryable message on network failure", async () => {
    await renderForm();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the server/i);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("shows backend field errors under the input", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Request validation failed.",
            details: {
              errors: [{ loc: ["body", "email"], message: "not a valid email", type: "value_error" }],
            },
          },
        },
        422,
      ),
    );

    await userEvent.type(screen.getByLabelText("Email"), "bad");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("not a valid email")).toBeInTheDocument();
  });
});

describe("concurrency", () => {
  it("prevents a double submission while pending", async () => {
    await renderForm();
    let resolveLogin: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveLogin = r)));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");

    const submit = screen.getByRole("button", { name: /sign in|signing in/i });
    await userEvent.click(submit);
    await waitFor(() => expect(submit).toBeDisabled());
    await userEvent.click(submit);
    await userEvent.click(submit);

    expect(loginCalls()).toHaveLength(1);
    expect(submit).toHaveAttribute("aria-busy", "true");

    resolveLogin?.(jsonResponse({ id: 1, email: "a@b.c" }));
    await waitFor(() => expect(replace).toHaveBeenCalled());
  });
});
