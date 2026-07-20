"use client";

/**
 * Workspace navigation.
 *
 * Every destination here is implemented, so all three are real links.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS = [
  { href: "/history", label: "History", description: "Review and compare past runs" },
  { href: "/datasets", label: "Datasets", description: "Manage saved price data" },
  { href: "/backtest/new", label: "New Backtest", description: "Import data and configure a run" },
] as const;

export function AppNavigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="Workspace sections">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Sections
      </h2>
      <ul className="mt-3 space-y-2">
        {SECTIONS.map((section) => {
          const current = pathname === section.href;
          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={current ? "page" : undefined}
                className={`block rounded-md border px-3 py-2.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 ${
                  current
                    ? "border-sky-700 bg-sky-50 dark:bg-sky-950"
                    : "border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                }`}
              >
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-sm font-medium">{section.label}</span>
                  {/* Current page stated in text, not by colour alone. */}
                  {current && (
                    <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-900 dark:bg-sky-900 dark:text-sky-100">
                      Current
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">
                  {section.description}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
