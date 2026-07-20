/**
 * Authentication and console-hygiene fixtures.
 *
 * Credentials are generated per test so runs never collide, and nothing
 * sensitive is ever printed: passwords, cookies, and tokens stay inside the
 * browser context.
 */

import { expect, test as base, type Page } from "@playwright/test";

export interface Credentials {
  email: string;
  password: string;
}

let counter = 0;

export function makeCredentials(prefix = "e2e"): Credentials {
  counter += 1;
  return {
    // example.com, not example.test: the backend's email validator rejects
    // special-use reserved TLDs, so `.test` would fail before reaching the app.
    email: `${prefix}.${Date.now()}.${counter}@example.com`,
    // A local throwaway value; never logged and never asserted on.
    password: "e2e-account-password",
  };
}

export async function registerAndLogin(
  page: Page,
  credentials: Credentials = makeCredentials(),
): Promise<Credentials> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByLabel("Confirm password").fill(credentials.password);
  await page.getByRole("button", { name: "Create account" }).click();

  // Registration deliberately does not sign the user in.
  await expect(page.getByText("Account created")).toBeVisible();
  await page.getByRole("link", { name: "Go to sign in" }).click();

  await login(page, credentials);
  return credentials;
}

export async function login(page: Page, credentials: Credentials): Promise<void> {
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/history$/);
}

/** Backend responses a test may deliberately provoke. */
export interface AllowedFailures {
  /** Status codes that are expected during this test. */
  statuses?: number[];
}

/**
 * Records page errors, console errors, and unexpected server responses so a
 * test can assert the flow was clean. Diagnostics never include cookies,
 * tokens, or response bodies.
 */
export interface PageDiagnostics {
  pageErrors: string[];
  consoleErrors: string[];
  badResponses: string[];
  assertClean: () => void;
}

const EXPECTED_BY_DEFAULT = new Set([401, 404, 409, 422]);

export function watchPage(page: Page, allowed: AllowedFailures = {}): PageDiagnostics {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const badResponses: string[] = [];
  const allowedStatuses = new Set([...EXPECTED_BY_DEFAULT, ...(allowed.statuses ?? [])]);

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Chrome logs its own "Failed to load resource" entry for every non-2xx
    // response. That is the browser narrating the network, not the app
    // reporting a fault, so a status the test already expects — a signed-out
    // 401 from /api/auth/me, say — must not read as a console error.
    const expectedNetworkNoise = /^Failed to load resource: the server responded with a status of (\d+)/.exec(
      message.text(),
    );
    if (expectedNetworkNoise && allowedStatuses.has(Number(expectedNetworkNoise[1]))) return;
    consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status < 400 || allowedStatuses.has(status)) return;
    // Path only — never the body, which could contain result data.
    badResponses.push(`${status} ${new URL(response.url()).pathname}`);
  });

  return {
    pageErrors,
    consoleErrors,
    badResponses,
    assertClean() {
      // React reports hydration mismatches through console.error, so this
      // assertion also covers them.
      expect(pageErrors, "uncaught page errors").toEqual([]);
      expect(consoleErrors, "console errors").toEqual([]);
      expect(badResponses, "unexpected server failures").toEqual([]);
    },
  };
}

/** A test with diagnostics wired up automatically. */
export const test = base.extend<{ diagnostics: PageDiagnostics }>({
  diagnostics: async ({ page }, use) => {
    const diagnostics = watchPage(page);
    await use(diagnostics);
  },
});

export { expect };
