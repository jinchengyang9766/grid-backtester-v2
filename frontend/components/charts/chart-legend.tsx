import { useId } from "react";

import type {
  BarSeries,
  ChartSeries,
  MarkerGroup,
} from "@/lib/backtests/chart-data";

/**
 * Legend swatches show each series' colour *and* its shape or dash pattern,
 * so the series stay distinguishable without relying on colour perception.
 */
export function ChartLegend({
  series = [],
  markers = [],
  bars = [],
  references = [],
}: {
  series?: readonly ChartSeries[];
  markers?: readonly MarkerGroup[];
  bars?: readonly BarSeries[];
  references?: readonly { label: string; color: string }[];
}) {
  // Pattern ids must not collide across the several charts on one page.
  // useId's delimiters are stripped so the value is safe inside `url(#…)`.
  const patternBase = `hatch${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

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
      {markers.map((group) => (
        <li key={group.key} className="flex items-center gap-1.5">
          {/* The same triangle the chart draws, so the glyph itself is the key. */}
          <svg width="14" height="12" viewBox="0 0 14 12" aria-hidden="true" className="shrink-0">
            <path
              d={
                group.shape === "triangle-up"
                  ? "M7,1.5 L12,10 L2,10 Z"
                  : "M7,10.5 L12,2 L2,2 Z"
              }
              fill={group.color}
              stroke="#ffffff"
              strokeWidth="0.6"
            />
          </svg>
          <span className="text-slate-700 dark:text-slate-300">{group.label}</span>
        </li>
      ))}
      {bars.map((band) => (
        <li key={band.key} className="flex items-center gap-1.5">
          <svg width="14" height="10" viewBox="0 0 14 10" aria-hidden="true" className="shrink-0">
            <defs>
              <pattern
                id={`${patternBase}-${band.key}`}
                width="3"
                height="3"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <rect width="3" height="3" fill={band.color} />
                <line x1="0" y1="0" x2="0" y2="3" stroke="#ffffff" strokeWidth="1.2" />
              </pattern>
            </defs>
            <rect
              width="14"
              height="10"
              fill={band.hatched ? `url(#legend-hatch-${band.key})` : band.color}
            />
          </svg>
          <span className="text-slate-700 dark:text-slate-300">{band.label}</span>
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
