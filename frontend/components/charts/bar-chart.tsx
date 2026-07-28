"use client";

/**
 * A small dependency-free stacked bar chart, for whole counts only.
 *
 * It plots tallies of persisted rows — never a price, a return, or any other
 * decimal — so nothing here can misstate a financial value. Bands are told
 * apart by a hatch pattern as well as by colour, and every caller shows the
 * same totals as text nearby.
 */

import { useId } from "react";

import { ChartEmptyState } from "@/components/charts/chart-empty-state";
import { ChartLegend } from "@/components/charts/chart-legend";
import { tickIndices, type BarSeries } from "@/lib/backtests/chart-data";

export interface BarChartProps {
  title: string;
  description: string;
  series: readonly BarSeries[];
  /** Axis tick labels, indexed like the counts. */
  labels: readonly string[];
  emptyMessage?: string;
  height?: number;
}

const WIDTH = 720;
const PLOT_LEFT = 74;
const PLOT_RIGHT = 12;
const PLOT_TOP = 12;
const PLOT_BOTTOM = 34;

export function BarChart({
  title,
  description,
  series,
  labels,
  emptyMessage = "No activity was recorded for this chart.",
  height = 200,
}: BarChartProps) {
  const titleId = useId();
  const descriptionId = useId();
  const patternBase = `bars${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  const columns = Math.max(0, ...series.map((band) => band.counts.length));
  const totals: number[] = [];
  for (let index = 0; index < columns; index += 1) {
    totals.push(series.reduce((sum, band) => sum + (band.counts[index] ?? 0), 0));
  }
  const peak = Math.max(0, ...totals);

  if (columns === 0 || peak === 0) {
    return <ChartEmptyState title={title}>{emptyMessage}</ChartEmptyState>;
  }

  const plotWidth = WIDTH - PLOT_LEFT - PLOT_RIGHT;
  const plotHeight = height - PLOT_TOP - PLOT_BOTTOM;
  const slot = plotWidth / columns;
  // Keep a hairline of separation on sparse axes, but never vanish on dense
  // ones — a 400-day run still has to show its single-trade days.
  const barWidth = Math.max(1, Math.min(slot * 0.7, 14));

  const toY = (value: number) => PLOT_TOP + plotHeight - (value / peak) * plotHeight;
  const toX = (index: number) => PLOT_LEFT + index * slot + slot / 2;

  // Whole counts only, so ticks are whole numbers and never repeat.
  const yTicks = [...new Set([0, Math.ceil(peak / 2), peak])];
  const xTicks = tickIndices(labels.length);

  return (
    <figure className="m-0">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      <div className="mt-2 w-full overflow-x-auto">
        <svg
          role="img"
          aria-labelledby={`${titleId} ${descriptionId}`}
          viewBox={`0 0 ${WIDTH} ${height}`}
          className="h-auto w-full min-w-[320px]"
          preserveAspectRatio="xMidYMid meet"
        >
          <title id={titleId}>{title}</title>
          <desc id={descriptionId}>{description}</desc>

          <defs>
            {series
              .filter((band) => band.hatched)
              .map((band) => (
                <pattern
                  key={band.key}
                  id={`${patternBase}-${band.key}`}
                  width="3"
                  height="3"
                  patternUnits="userSpaceOnUse"
                  patternTransform="rotate(45)"
                >
                  <rect width="3" height="3" fill={band.color} />
                  <line x1="0" y1="0" x2="0" y2="3" stroke="#ffffff" strokeWidth="1.2" />
                </pattern>
              ))}
          </defs>

          <rect
            x={PLOT_LEFT}
            y={PLOT_TOP}
            width={plotWidth}
            height={plotHeight}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            className="text-slate-400"
          />

          {yTicks.map((value) => (
            <g key={`y-${value}`}>
              <line
                x1={PLOT_LEFT}
                y1={toY(value)}
                x2={PLOT_LEFT + plotWidth}
                y2={toY(value)}
                stroke="currentColor"
                strokeWidth="0.3"
                className="text-slate-300 dark:text-slate-700"
              />
              <text
                x={PLOT_LEFT - 6}
                y={toY(value) + 3}
                textAnchor="end"
                fontSize="9"
                fill="currentColor"
                className="text-slate-600 dark:text-slate-400"
              >
                {String(value)}
              </text>
            </g>
          ))}

          {Array.from({ length: columns }, (_, index) => {
            let baseline = 0;
            return (
              <g key={`column-${index}`}>
                {series.map((band) => {
                  const count = band.counts[index] ?? 0;
                  if (count === 0) return null;
                  const top = toY(baseline + count);
                  const bottom = toY(baseline);
                  baseline += count;
                  return (
                    <rect
                      key={band.key}
                      x={toX(index) - barWidth / 2}
                      y={top}
                      width={barWidth}
                      height={Math.max(0.8, bottom - top)}
                      fill={band.hatched ? `url(#${patternBase}-${band.key})` : band.color}
                    />
                  );
                })}
              </g>
            );
          })}

          {xTicks.map((index, position) => (
            <text
              key={`x-${index}`}
              x={toX(index)}
              y={height - 12}
              // Matches the line charts: end ticks anchor inwards so a date
              // near the plot edge is never clipped by the viewBox.
              textAnchor={
                position === 0 ? "start" : position === xTicks.length - 1 ? "end" : "middle"
              }
              fontSize="9"
              fill="currentColor"
              className="text-slate-600 dark:text-slate-400"
            >
              {labels[index] ?? ""}
            </text>
          ))}
        </svg>
      </div>
      <ChartLegend bars={series} />
    </figure>
  );
}
