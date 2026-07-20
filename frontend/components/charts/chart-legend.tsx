import type { ChartSeries } from "@/lib/backtests/chart-data";

/**
 * Legend swatches show each series' colour *and* its dash pattern, so the
 * series stay distinguishable without relying on colour perception.
 */
export function ChartLegend({
  series,
  references = [],
}: {
  series: readonly ChartSeries[];
  references?: readonly { label: string; color: string }[];
}) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {series.map((entry) => (
        <li key={entry.key} className="flex items-center gap-1.5">
          <svg width="22" height="8" aria-hidden="true" className="shrink-0">
            <line
              x1="0"
              y1="4"
              x2="22"
              y2="4"
              stroke={entry.color}
              strokeWidth="2"
              strokeDasharray={entry.dash}
            />
          </svg>
          <span className="text-slate-700 dark:text-slate-300">{entry.label}</span>
        </li>
      ))}
      {references.map((reference) => (
        <li key={reference.label} className="flex items-center gap-1.5">
          <svg width="22" height="8" aria-hidden="true" className="shrink-0">
            <line
              x1="0"
              y1="4"
              x2="22"
              y2="4"
              stroke={reference.color}
              strokeWidth="1"
              strokeDasharray="3 2"
            />
          </svg>
          <span className="text-slate-700 dark:text-slate-300">{reference.label}</span>
        </li>
      ))}
    </ul>
  );
}
