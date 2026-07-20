import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegisterForm } from "@/components/auth/register-form";
import { AuthProvider } from "@/lib/auth/auth-context";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
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
  fetchMock = vi.fn().mockResolvedValue(jsonResponse(UNAUTHENTICATED_BODY, 401));
  vi.stubGlobal("fetch", fetchMock);
});

async function renderForm() {
  render(
    <AuthProvider>
      <RegisterForm />
    </AuthProvider>,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
}

function registerCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/auth/register"));
}

async function fillAndSubmit(email: string, password: string, confirm: string) {
  // userEvent.type rejects an empty string, so a blank field is left untouched.
  if (email) await userEvent.type(screen.getByLabelText("Email"), email);
  if (password) await userEvent.type(screen.getByLabelText("Password"), password);
  if (confirm) await userEvent.type(screen.getByLabelText("Confirm password"), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Create account" }));
}

describe("fields and accessibility", () => {
  it("uses new-password autocomplete on both password fields", async () => {
    await renderForm();
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "email");
  });

  it("links to the login page", async () => {
    await renderForm();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("states the minimum password length", async () => {
    await renderForm();
    expect(screen.getByText("At least 8 characters.")).toBeInTheDocument();
  });
});

describe("validation", () => {
  it("rejects a password shorter than eight characters", async () => {
    await renderForm();
    await fillAndSubmit("a@b.c", "short12", "short12");

    expect(
      await screen.findByText("Password must be at least 8 characters."),
    ).toBeInTheDocument();
    expect(registerCalls()).toHaveLength(0);
  });

  it("accepts an eight-character password with no complexity rule", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: 1, email: "a@b.c", created_at: "2026-01-01T00:00:00Z" }, 201),
    );
    // All lowercase letters: no uppercase/digit/symbol requirement exists.
    await fillAndSubmit("a@b.c", "abcdefgh", "abcdefgh");

    await waitFor(() => expect(registerCalls()).toHaveLength(1));
    expect(screen.queryByText(/must contain/i)).not.toBeInTheDocument();
  });

  it("rejects a mismatched confirmation", async () => {
    await renderForm();
    await fillAndSubmit("a@b.c", "secret123", "secret124");

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(registerCalls()).toHaveLength(0);
  });

  it("requires an email address", async () => {
    await renderForm();
    await fillAndSubmit("", "secret123", "secret123");

    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(registerCalls()).toHaveLength(0);
  });
});

describe("submission", () => {
  it("sends only email and password", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: 1, email: "a@b.c", created_at: "2026-01-01T00:00:00Z" }, 201),
    );
    await fillAndSubmit("a@b.c", "secret123", "secret123");

    await waitFor(() => expect(registerCalls()).toHaveLength(1));
    const body = JSON.parse(String((registerCalls()[0][1] as RequestInit).body));
    expect(body).toEqual({ email: "a@b.c", password: "secret123" });
    expect(body).not.toHaveProperty("confirmPassword");
  });

  it("shows success without pretending the user is signed in", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: 1, email: "a@b.c", created_at: "2026-01-01T00:00:00Z" }, 201),
    );
    await fillAndSubmit("a@b.c", "secret123", "secret123");

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Account created");
    expect(status).toHaveTextContent("a@b.c");
    // Directs to sign in rather than entering the app.
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("button", { name: "Create account" })).not.toBeInTheDocument();
  });

  it("shows the safe backend message for a duplicate email", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "EMAIL_ALREADY_REGISTERED",
            message: "This email is already registered.",
          },
        },
        409,
      ),
    );
    await fillAndSubmit("a@b.c", "secret123", "secret123");

    expect(await screen.findByRole("alert")).toHaveTextContent("This email is already registered.");
  });

  it("clears both password fields after a failure", async () => {
    await renderForm();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "EMAIL_ALREADY_REGISTERED", message: "This email is already registered." } },
        409,
      ),
    );
    await fillAndSubmit("a@b.c", "secret123", "secret123");

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm password")).toHaveValue("");
  });

  it("shows a safe message on network failure", async () => {
    await renderForm();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await fillAndSubmit("a@b.c", "secret123", "secret123");

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the server/i);
  });

  it("prevents a double submission while pending", async () => {
    await renderForm();
    let resolveRegister: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveRegister = r)));

    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.type(screen.getByLabelText("Confirm password"), "secret123");

    const submit = screen.getByRole("button", { name: /create account|creating account/i });
    await userEvent.click(submit);
    await waitFor(() => expect(submit).toBeDisabled());
    await userEvent.click(submit);

    expect(registerCalls()).toHaveLength(1);

    resolveRegister?.(
      jsonResponse({ id: 1, email: "a@b.c", created_at: "2026-01-01T00:00:00Z" }, 201),
    );
    await screen.findByRole("status");
  });
});
