import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExportControls } from "@/components/results/export-controls";

const EXPECTED = [
  ["Download trades CSV", "/api/backtests/5/exports/trades.csv"],
  ["Download equity CSV", "/api/backtests/5/exports/equity.csv"],
  ["Download complete result JSON", "/api/backtests/5/exports/result.json"],
  ["Download PDF report", "/api/backtests/5/exports/report.pdf"],
] as const;

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("export links", () => {
  it("renders exactly the four backend exports", () => {
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(4);
    for (const [label, href] of EXPECTED) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("uses the numeric id and never the editable run name", () => {
    render(<ExportControls backtestId={42} status="COMPLETED" />);
    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href") ?? "";
      expect(href).toMatch(/^\/api\/backtests\/42\/exports\//);
      // Relative, same-origin, and carrying no name or token.
      expect(href).not.toMatch(/^https?:/);
      expect(href).not.toContain("?");
      expect(href).not.toContain("name=");
      expect(href).not.toContain("token");
    }
  });

  it("marks each link as a download with a unique accessible name", () => {
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    const names = screen.getAllByRole("link").map((link) => link.textContent);
    expect(new Set(names).size).toBe(4);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAttribute("download");
    }
  });

  it("explains that files are generated on demand", () => {
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    expect(screen.getByText(/generated when you select it/i)).toBeInTheDocument();
  });

  it("fetches nothing on render — no export is generated until activation", () => {
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("run status", () => {
  it("still offers downloads for a FAILED run, with a caveat", () => {
    render(<ExportControls backtestId={5} status="FAILED" />);
    // Ownership is the backend's only export gate, so no control is disabled.
    expect(screen.getAllByRole("link")).toHaveLength(4);
    expect(screen.getByText(/headers only/i)).toBeInTheDocument();
  });

  it.each(["PENDING", "RUNNING"])("offers downloads for a %s run", (status) => {
    render(<ExportControls backtestId={5} status={status} />);
    expect(screen.getAllByRole("link")).toHaveLength(4);
  });

  it("adds no caveat for a completed run", () => {
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    expect(screen.queryByText(/headers only/i)).not.toBeInTheDocument();
  });
});

describe("download implementation", () => {
  it("creates no object URL and reads no file body", async () => {
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    render(<ExportControls backtestId={5} status="COMPLETED" />);
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it("uses plain anchors rather than script-driven downloads", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(
      join(__dirname, "..", "components", "results", "export-controls.tsx"),
      "utf8",
    )
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");

    // No script-driven download path at all.
    expect(source).not.toMatch(/fetch\(/);
    expect(source).not.toMatch(/createObjectURL|revokeObjectURL/);
    expect(source).not.toMatch(/FileReader|Blob\(/);
    expect(source).not.toMatch(/onClick/);
    // Rendered as real links.
    expect(source).toMatch(/<a\s/);
  });
});
