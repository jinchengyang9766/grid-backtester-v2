"use client";

/**
 * A small dependency-free SVG line chart.
 *
 * Points are plotted in their persisted order with straight segments — no
 * smoothing, no interpolation, and no invented points, so the picture cannot
 * imply data the backend never produced.
 *
 * The chart is decorative for assistive technology: every caller renders an
 * accessible table of the same stored strings beside it, which is also what
 * keyboard users reach.
 */

import { useId } from "react";

import { ChartEmptyState } from "@/components/charts/chart-empty-state";
import { ChartLegend } from "@/components/charts/chart-legend";
import {
  chartRange,
  tickIndices,
  type ChartSeries,
} from "@/lib/backtests/chart-data";

export interface ReferenceLine {
  label: string;
  /** Already a plot coordinate; the caller converts at the adapter. */
  value: number;
  color: string;
  /** Rendered faintly and unlabelled, e.g. individual grid levels. */
  faint?: boolean;
}

export interface LineChartProps {
  title: string;
  description: string;
  series: readonly ChartSeries[];
  /** Axis tick labels, indexed like the series points. */
  labels: readonly string[];
  referenceLines?: readonly ReferenceLine[];
  /** Formats a y-axis tick from its numeric coordinate. */
  formatValue?: (value: number) => string;
  emptyMessage?: string;
  height?: number;
}

const WIDTH = 720;
const PLOT_LEFT = 74;
const PLOT_RIGHT = 12;
const PLOT_TOP = 12;
const PLOT_BOTTOM = 34;

function defaultFormat(value: number): string {
  // Axis ticks are derived coordinates, not reported figures, so a compact
  // rendering here cannot misstate a stored value.
  const magnitude = Math.abs(value);
  if (magnitude !== 0 && magnitude < 0.001) return value.toExponential(1);
  const decimals = magnitude >= 1000 ? 0 : magnitude >= 1 ? 2 : 4;
  return value.toFixed(decimals);
}

export function LineChart({
  title,
  description,
  series,
  labels,
  referenceLines = [],
  formatValue = defaultFormat,
  emptyMessage = "No data was recorded for this chart.",
  height = 260,
}: LineChartProps) {
  const titleId = useId();
  const descriptionId = useId();

  const plotted = series.filter((entry) => entry.points.length > 0);
  const range = chartRange(
    plotted,
    referenceLines.map((line) => line.value),
  );

  if (plotted.length === 0 || range === null) {
    return <ChartEmptyState title={title}>{emptyMessage}</ChartEmptyState>;
  }

  const plotWidth = WIDTH - PLOT_LEFT - PLOT_RIGHT;
  const plotHeight = height - PLOT_TOP - PLOT_BOTTOM;
  const span = range.max - range.min;

  const toY = (value: number) =>
    PLOT_TOP + plotHeight - ((value - range.min) / span) * plotHeight;
  const toX = (index: number) =>
    range.count <= 1
      ? PLOT_LEFT + plotWidth / 2
      : PLOT_LEFT + (index / (range.count - 1)) * plotWidth;

  const yTicks = [0, 1, 2, 3, 4].map((step) => range.min + (span * step) / 4);
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
                {formatValue(value)}
              </text>
            </g>
          ))}

          {referenceLines.map((line) => (
            <g key={`${line.label}-${line.value}`}>
              <line
                x1={PLOT_LEFT}
                y1={toY(line.value)}
                x2={PLOT_LEFT + plotWidth}
                y2={toY(line.value)}
                stroke={line.color}
                strokeWidth={line.faint ? 0.4 : 0.9}
                strokeDasharray="4 3"
                opacity={line.faint ? 0.5 : 1}
              />
              {!line.faint && (
                <text
                  x={PLOT_LEFT + plotWidth - 3}
                  y={toY(line.value) - 3}
                  textAnchor="end"
                  fontSize="8"
                  fill={line.color}
                >
                  {line.label}
                </text>
              )}
            </g>
          ))}

          {plotted.map((entry) => {
            if (entry.points.length === 1) {
              // A single point has no segment; mark it so it is still visible.
              const only = entry.points[0];
              return (
                <circle
                  key={entry.key}
                  cx={toX(only.index)}
                  cy={toY(only.value)}
                  r="3"
                  fill={entry.color}
                />
              );
            }
            const path = entry.points
              .map(
                (point, position) =>
                  `${position === 0 ? "M" : "L"}${toX(point.index).toFixed(2)},${toY(point.value).toFixed(2)}`,
              )
              .join(" ");
            return (
              <path
                key={entry.key}
                d={path}
                fill="none"
                stroke={entry.color}
                strokeWidth="1.2"
                strokeDasharray={entry.dash}
              />
            );
          })}

          {xTicks.map((index) => (
            <text
              key={`x-${index}`}
              x={toX(index)}
              y={height - 12}
              textAnchor="middle"
              fontSize="9"
              fill="currentColor"
              className="text-slate-600 dark:text-slate-400"
            >
              {labels[index] ?? ""}
            </text>
          ))}
        </svg>
      </div>
      <ChartLegend
        series={plotted}
        references={referenceLines
          .filter((line) => !line.faint)
          .map((line) => ({ label: line.label, color: line.color }))}
      />
    </figure>
  );
}
