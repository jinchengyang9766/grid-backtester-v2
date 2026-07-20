/**
 * The workspace navigation.
 *
 * Every destination beyond the overview is still unimplemented, so those
 * entries render as disabled text rather than links — a clickable route that
 * 404s would be worse than an honest "coming soon".
 */

const PLANNED_SECTIONS = [
  { label: "Datasets", description: "Upload and manage price data" },
  { label: "New Backtest", description: "Configure and run a strategy" },
  { label: "Backtest History", description: "Review and compare past runs" },
] as const;

export function AppNavigation() {
  return (
    <nav aria-label="Workspace sections">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Sections
      </h2>
      <ul className="mt-3 space-y-2">
        {PLANNED_SECTIONS.map((section) => (
          <li key={section.label}>
            <div
              className="rounded-md border border-dashed border-slate-300 px-3 py-2.5 dark:border-slate-700"
              aria-disabled="true"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                  {section.label}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  Not available yet
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {section.description}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </nav>
  );
}
