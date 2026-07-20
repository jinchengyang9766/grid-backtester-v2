import { EMPTY_VALUE } from "@/lib/datasets/display";
import {
  decimalTimesHundred,
  isDecimalString,
  trimTrailingZeros,
  truncateDecimal,
} from "@/lib/backtests/decimal-string";
import type { MetricRow, MetricSection } from "@/lib/backtests/metrics";

/** Fractional digits kept in the parenthesised percentage hint. */
const PERCENT_HINT_PLACES = 4;

/**
 * Render one stored metric.
 *
 * The stored string is always shown verbatim and first. For a ratio, a short
 * percentage hint follows, produced by shifting digits (never multiplying
 * through a float) and truncated for readability — marked with "≈" whenever
 * digits were dropped, so the shortened form is never mistaken for the value.
 */
export function metricText(row: MetricRow): string {
  if (row.value === null) return EMPTY_VALUE;
  if (!row.ratio || !isDecimalString(row.value)) return row.value;

  const percent = decimalTimesHundred(row.value);
  if (percent === null) return row.value;

  const { text, truncated } = truncateDecimal(percent, PERCENT_HINT_PLACES);
  const hint = trimTrailingZeros(text);
  return `${row.value} (${truncated ? "≈" : ""}${hint}%)`;
}

export function MetricGrid({ rows }: { rows: readonly MetricRow[] }) {
  return (
    <dl className="grid gap-x-6 gap-y-1.5 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">{row.label}</dt>
          <dd className="text-right font-medium tabular-nums break-words">
            {metricText(row)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function MetricSectionBlock({ section }: { section: MetricSection }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{section.title}</h3>
      <MetricGrid rows={section.rows} />
    </section>
  );
}
