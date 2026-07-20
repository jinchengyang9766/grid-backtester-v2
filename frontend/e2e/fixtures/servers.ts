/**
 * Isolated backend + frontend lifecycle for the E2E suite.
 *
 * Every run gets its own temporary SQLite database outside the repository and
 * a freshly generated auth secret, so the suite never touches a developer's
 * data and cannot be made to pass by leftover state. Both servers are stopped
 * and the database removed even when tests fail.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const BACKEND_PORT = 8123;
export const FRONTEND_PORT = 3123;
export const BASE_URL = `http://127.0.0.1:${FRONTEND_PORT}`;

const REPO_ROOT = join(__dirname, "..", "..", "..");
const BACKEND_DIR = join(REPO_ROOT, "backend");
const FRONTEND_DIR = join(REPO_ROOT, "frontend");

/** The venv interpreter this project uses on Windows and POSIX alike. */
function pythonExecutable(): string {
  const windows = join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
  const posix = join(BACKEND_DIR, ".venv", "bin", "python");
  return existsSync(windows) ? windows : posix;
}

async function waitForOk(url: string, timeoutMs = 120_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status === 401) return;
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function stop(child: ChildProcess | null): Promise<void> {
  if (child === null || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    child.once("exit", () => resolve());
    // Windows needs the whole process tree taken down.
    if (process.platform === "win32" && child.pid !== undefined) {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGTERM");
    }
    setTimeout(resolve, 5_000);
  });
}

export interface RunningServers {
  shutdown: () => Promise<void>;
}

export async function startServers(): Promise<RunningServers> {
  const workDir = mkdtempSync(join(tmpdir(), "grid-e2e-"));
  const databasePath = join(workDir, "e2e.db").replace(/\\/g, "/");
  // Generated per run; never a shared or committed value.
  const authSecret = randomBytes(32).toString("hex");

  const python = pythonExecutable();
  const backendEnv = {
    ...process.env,
    GRID_BACKTESTER_DATABASE_URL: `sqlite:///${databasePath}`,
    GRID_BACKTESTER_AUTH_SECRET_KEY: authSecret,
    GRID_BACKTESTER_APP_ENVIRONMENT: "development",
  };

  // Create the schema before serving, so the first request never races it.
  await new Promise<void>((resolve, reject) => {
    const create = spawn(
      python,
      [
        "-c",
        [
          "from app.db import Base",
          "from app.db.session import create_database_engine",
          `Base.metadata.create_all(create_database_engine("sqlite:///${databasePath}"))`,
        ].join("; "),
      ],
      { cwd: BACKEND_DIR, env: backendEnv, stdio: "ignore" },
    );
    create.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`schema creation failed (${code})`)),
    );
    create.on("error", reject);
  });

  const backend = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(BACKEND_PORT),
      "--log-level",
      "warning",
    ],
    { cwd: BACKEND_DIR, env: backendEnv, stdio: "ignore" },
  );

  // Next's CLI is invoked through Node directly rather than through `npm`:
  // spawning npm.cmd on Windows requires a shell, which brings quoting risks.
  const frontend = spawn(
    process.execPath,
    [join(FRONTEND_DIR, "node_modules", "next", "dist", "bin", "next"), "start", "--port", String(FRONTEND_PORT)],
    {
      cwd: FRONTEND_DIR,
      env: { ...process.env, BACKEND_ORIGIN: `http://127.0.0.1:${BACKEND_PORT}` },
      stdio: "ignore",
    },
  );

  const shutdown = async () => {
    await stop(frontend);
    await stop(backend);
    // Remove the temporary database and its directory, pass or fail.
    try {
      rmSync(workDir, { recursive: true, force: true });
    } catch {
      // A locked file on Windows must not fail the suite.
    }
  };

  try {
    await waitForOk(`http://127.0.0.1:${BACKEND_PORT}/health`);
    await waitForOk(`${BASE_URL}/login`);
  } catch (error) {
    await shutdown();
    throw error;
  }

  return { shutdown };
}
