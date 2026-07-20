/**
 * Export downloads for one owned backtest (SPEC Sections 25.4, 31).
 *
 * These are ordinary same-origin anchors, not fetch-and-Blob buttons, and
 * that is deliberate:
 *
 *   - The browser performs the download natively, so the `HttpOnly` session
 *     cookie is attached automatically and the backend's own
 *     `Content-Disposition` filename is honoured.
 *   - Nothing is generated until the user activates a link; the server builds
 *     each file on demand.
 *   - CSV and PDF bytes are never decoded into JavaScript. Reading a report
 *     into memory only to hand it straight back to the browser would waste
 *     memory, risk corrupting binary content, and gain nothing.
 *
 * Paths use the numeric run id only — never the user-editable run name.
 */

const EXPORTS = [
  {
    file: "trades.csv",
    label: "Download trades CSV",
    description: "One row per trade, in event order.",
  },
  {
    file: "equity.csv",
    label: "Download equity CSV",
    description: "One row per trading day of the daily close equity series.",
  },
  {
    file: "result.json",
    label: "Download complete result JSON",
    description: "Configuration, metrics, both benchmarks, and the dataset summary.",
  },
  {
    file: "report.pdf",
    label: "Download PDF report",
    description: "A printable summary with charts and the first 20 trades.",
  },
] as const;

const LINK_CLASS =
  "inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700";

export function ExportControls({
  backtestId,
  status,
}: {
  backtestId: number;
  status: string;
}) {
  // Ownership is the backend's only export gate, so a run that did not
  // complete still exports — its series are simply empty.
  const incomplete = status !== "COMPLETED";

  return (
    <section aria-labelledby="exports-heading" className="space-y-3">
      <div>
        <h2 id="exports-heading" className="text-base font-semibold">
          Downloads
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Each file is generated when you select it and is never stored on the
          server.
          {incomplete &&
            " This run has no stored results, so the data files will contain headers only."}
        </p>
      </div>

      <ul className="flex flex-wrap gap-2">
        {EXPORTS.map((entry) => (
          <li key={entry.file}>
            <a
              href={`/api/backtests/${backtestId}/exports/${entry.file}`}
              // The backend already sends Content-Disposition: attachment;
              // `download` keeps the intent explicit for the browser.
              download
              className={LINK_CLASS}
              title={entry.description}
            >
              {entry.label}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
