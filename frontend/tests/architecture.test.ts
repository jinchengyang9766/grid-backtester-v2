import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
const SOURCE_DIRS = ["app", "components", "lib"];

function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry)) {
        found.push(full);
      }
    }
  };
  for (const dir of SOURCE_DIRS) walk(join(ROOT, dir));
  return found;
}

function read(file: string): string {
  return readFileSync(file, "utf8");
}

/**
 * Drop comments so these checks assert on executable code. The modules
 * deliberately *document* that they avoid localStorage and JWT decoding, and
 * that prose must not be mistaken for the behaviour it warns against.
 */
function code(file: string): string {
  return read(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const FILES = sourceFiles();

describe("token handling", () => {
  it("never touches localStorage or sessionStorage", () => {
    for (const file of FILES) {
      const source = code(file);
      expect(source, relative(ROOT, file)).not.toMatch(/localStorage/);
      expect(source, relative(ROOT, file)).not.toMatch(/sessionStorage/);
    }
  });

  it("never sets an Authorization header or builds a Bearer token", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      // Setting the header, in either headers.set(...) or object-literal form.
      expect(source, name).not.toMatch(/headers\.(set|append)\(\s*["'`]authorization/i);
      expect(source, name).not.toMatch(/["'`]Authorization["'`]\s*:/i);
      expect(source, name).not.toMatch(/Bearer/i);
    }
  });

  it("never reads or decodes the access token in JavaScript", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      // The cookie is HttpOnly, so document.cookie could never see it anyway.
      expect(source, name).not.toMatch(/document\.cookie/);
      expect(source, name).not.toMatch(/jwtDecode|decodeToken|atob\(/i);
    }
  });
});

describe("scope of this slice", () => {
  it("ships no Dataset or Backtest API client", () => {
    const apiModules = FILES.filter((file) => file.includes(join("lib", "api")));
    const names = apiModules.map((file) => relative(ROOT, file).replace(/\\/g, "/"));
    expect(names.sort()).toEqual([
      "lib/api/auth.ts",
      "lib/api/client.ts",
      "lib/api/errors.ts",
      "lib/api/types.ts",
    ]);

    for (const file of FILES) {
      const source = read(file);
      expect(source).not.toMatch(/\/api\/datasets/);
      expect(source).not.toMatch(/\/api\/backtests/);
      expect(source).not.toMatch(/\/api\/optimizations/);
    }
  });

  it("adds no charting or data-fetching library", () => {
    const pkg = JSON.parse(read(join(ROOT, "package.json"))) as {
      dependencies: Record<string, string>;
      devDependencies: Record<string, string>;
    };
    const all = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    for (const banned of [
      "axios",
      "recharts",
      "chart.js",
      "d3",
      "lightweight-charts",
      "swr",
      "@tanstack/react-query",
      "redux",
      "zustand",
      "mobx",
      "react-hook-form",
      "zod",
      "yup",
      "formik",
      "@mui/material",
      "antd",
      "next-auth",
    ]) {
      expect(all, `${banned} must not be a dependency`).not.toContain(banned);
    }
  });

  it("keeps runtime dependencies to the framework itself", () => {
    const pkg = JSON.parse(read(join(ROOT, "package.json"))) as {
      dependencies: Record<string, string>;
    };
    expect(Object.keys(pkg.dependencies).sort()).toEqual(["next", "react", "react-dom"]);
  });
});

describe("api call surface", () => {
  it("only ever calls same-origin relative /api paths", () => {
    for (const file of FILES) {
      const source = read(file);
      // The proxy route itself is the one place a backend origin appears.
      if (file.includes(join("app", "api"))) continue;
      expect(source, relative(ROOT, file)).not.toMatch(/fetch\(\s*["'`]https?:\/\//);
      expect(source, relative(ROOT, file)).not.toMatch(/127\.0\.0\.1|localhost:\d+/);
    }
  });

  it("does not hard-code a production backend hostname in the proxy", () => {
    const proxyPath = join(ROOT, "app", "api", "[...path]", "route.ts");
    const proxy = code(proxyPath);
    expect(proxy).toContain("process.env.BACKEND_ORIGIN");
    // Only the documented loopback default may appear in executable code.
    const hosts = proxy.match(/https?:\/\/[\w.-]+(:\d+)?/g) ?? [];
    expect(hosts).toEqual(["http://127.0.0.1:8000"]);
    // A NEXT_PUBLIC_ variable would be inlined into the browser bundle.
    expect(proxy).not.toMatch(/NEXT_PUBLIC_/);
  });
});

describe("environment files", () => {
  it("documents BACKEND_ORIGIN without a NEXT_PUBLIC_ prefix", () => {
    const example = read(join(ROOT, ".env.example"));
    expect(example).toMatch(/^BACKEND_ORIGIN=/m);
    expect(example).not.toMatch(/NEXT_PUBLIC_BACKEND_ORIGIN=/);
  });

  it("contains no secret or token value", () => {
    const example = read(join(ROOT, ".env.example"));
    expect(example).not.toMatch(/SECRET|PASSWORD|TOKEN=/i);
  });

  it("ignores real env files but keeps the example tracked", () => {
    const ignore = read(join(ROOT, ".gitignore"));
    expect(ignore).toMatch(/^\.env\*$/m);
    expect(ignore).toMatch(/^!\.env\.example$/m);
    expect(ignore).toMatch(/\.next/);
    expect(ignore).toMatch(/node_modules/);
  });
});
