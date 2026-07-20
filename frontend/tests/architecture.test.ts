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
  it("ships only the auth, dataset, and backtest API clients", () => {
    const apiModules = FILES.filter((file) => file.includes(join("lib", "api")));
    const names = apiModules.map((file) => relative(ROOT, file).replace(/\\/g, "/"));
    expect(names.sort()).toEqual([
      "lib/api/auth.ts",
      "lib/api/backtest-history-types.ts",
      "lib/api/backtest-history.ts",
      "lib/api/backtest-types.ts",
      "lib/api/backtests.ts",
      "lib/api/client.ts",
      "lib/api/dataset-types.ts",
      "lib/api/datasets.ts",
      "lib/api/errors.ts",
      "lib/api/types.ts",
    ]);
  });

  it("calls no optimization or export endpoint", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      expect(source, name).not.toMatch(/["'`]\/api\/optimizations/);
      // Export download controls belong to a later task.
      expect(source, name).not.toMatch(/\/exports\//);
      expect(source, name).not.toMatch(/trades\.csv|equity\.csv|result\.json|report\.pdf/);
    }
  });

  it("never requests raw price bars", () => {
    for (const file of FILES) {
      const source = code(file);
      expect(source, relative(ROOT, file)).not.toMatch(/price_bars|priceBars/);
    }
  });

  it("never parses or cleans price data in the browser", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      // A second implementation here could disagree with the rows a preview
      // token is bound to, or with the executed prices.
      expect(source, name).not.toMatch(/parseCsv|cleanRows/);
      // No grid or engine simulation. Matched as identifiers, so ordinary
      // prose such as the risk disclaimer's "simulated" is not a hit.
      expect(source, name).not.toMatch(/\b(generateGrid|buildGridLevels|runEngine)\b/);
      expect(source, name).not.toMatch(/\bsimulate[A-Z]\w*\(/);
    }
  });

  it("converts a financial value to a number only in the chart adapter", () => {
    // The one module allowed to convert, and only to obtain SVG coordinates.
    const ADAPTER = join("lib", "backtests", "chart-data.ts");

    const financial = FILES.filter(
      (file) =>
        file.includes(join("lib", "backtests")) ||
        file.includes(join("components", "backtests")) ||
        file.includes(join("components", "results")),
    );
    expect(financial.length).toBeGreaterThan(0);

    for (const file of financial) {
      if (file.endsWith(ADAPTER)) continue;
      const source = code(file);
      const name = relative(ROOT, file);
      expect(source, name).not.toMatch(/parseFloat|Number\.parseFloat/);
      expect(source, name).not.toMatch(/toFixed\(/);
      // Number(...) as a conversion; Number.isSafeInteger etc. are fine.
      expect(source, name).not.toMatch(/[^.\w]Number\(/);
    }

    const adapter = code(join(ROOT, ADAPTER));
    expect(adapter).toMatch(/Number\(value\)/);
    expect(adapter).not.toMatch(/parseFloat/);
  });

  it("keeps chart geometry out of the metric and table modules", () => {
    // Only the chart components may import the coordinate adapter.
    for (const file of FILES) {
      if (file.includes(join("components", "charts"))) continue;
      if (file.endsWith(join("lib", "backtests", "chart-data.ts"))) continue;
      const source = code(file);
      const name = relative(ROOT, file);
      if (source.includes("chart-data")) {
        // Chart wrappers live under components/charts; anything else that
        // reaches for the adapter would be converting outside the boundary.
        expect(name, name).toMatch(/charts|history|results/);
      }
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

describe("upload and token handling", () => {
  it("never persists the selected file or the preview token", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      expect(source, name).not.toMatch(/indexedDB|IDBDatabase/i);
      expect(source, name).not.toMatch(/caches\.open|CacheStorage/);
      expect(source, name).not.toMatch(/showSaveFilePicker|FileSystemHandle/);
      // localStorage/sessionStorage are already banned globally above.
    }
  });

  it("never puts a preview token in a URL or the DOM", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      // Only `dataset_id` may travel in the query string.
      expect(source, name).not.toMatch(/[?&]preview_token=/);
      expect(source, name).not.toMatch(/searchParams\.set\(\s*["'`]preview_token/);
      expect(source, name).not.toMatch(/data-preview-token/);
    }
  });

  it("never logs request material", () => {
    for (const file of FILES) {
      const source = code(file);
      expect(source, relative(ROOT, file)).not.toMatch(/console\.(log|info|debug|warn|error)/);
    }
  });

  it("contains no chart or table library import", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      expect(source, name).not.toMatch(
        /from\s+["'](recharts|chart\.js|d3|plotly|lightweight-charts|@tanstack\/react-table)/,
      );
    }
  });

  it("persists no strategy configuration in the browser", () => {
    const strategyModules = FILES.filter(
      (file) =>
        file.includes(join("lib", "backtests")) ||
        file.includes(join("components", "backtests")),
    );
    for (const file of strategyModules) {
      const source = code(file);
      const name = relative(ROOT, file);
      expect(source, name).not.toMatch(/localStorage|sessionStorage|indexedDB/i);
    }
  });

  it("never puts a configuration or metric in a URL", () => {
    for (const file of FILES) {
      const source = code(file);
      const name = relative(ROOT, file);
      // Only dataset_id and backtest_id may appear as query parameters.
      expect(source, name).not.toMatch(/[?&]configuration=/);
      expect(source, name).not.toMatch(/[?&]result_metrics=/);
      expect(source, name).not.toMatch(/[?&]initial_cash=/);
    }
  });

  it("builds no export or optimization page", () => {
    // Route files only: basename exactly "page.tsx" under app/. A component
    // merely named "...-page.tsx" is not a route.
    const routes = FILES.map((file) => relative(ROOT, file).replace(/\\/g, "/")).filter(
      (path) => path.startsWith("app/") && path.endsWith("/page.tsx"),
    );
    expect(routes.sort()).toEqual([
      "app/app/page.tsx",
      "app/backtest/new/page.tsx",
      "app/datasets/page.tsx",
      "app/history/[backtestId]/page.tsx",
      "app/history/compare/page.tsx",
      "app/history/page.tsx",
      "app/login/page.tsx",
      "app/page.tsx",
      "app/register/page.tsx",
    ]);
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
