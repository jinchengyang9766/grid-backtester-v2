/**
 * The chart-coordinate boundary.
 *
 * This module is the ONLY place a stored decimal string becomes a JavaScript
 * number, and the result is used solely to compute an SVG coordinate. An SVG
 * path needs finite numbers, and a pixel is far coarser than the precision
 * lost by the conversion, so plotting through float is safe here — while the
 * same conversion anywhere in a label, table cell, or metric would silently
 * corrupt a reported value.
 *
 * Every helper keeps the original string alongside the coordinate value, so
 * tooltips and the accessible tables that accompany each chart continue to
 * show exactly what the backend stored.
 */

import { isDecimalString } from "./decimal-string";

export interface ChartPoint {
  /** Position along the x axis, by index into the series. */
  index: number;
  /** The plotted magnitude. Finite by construction. */
  value: number;
  /** The exact stored string this coordinate came from. */
  source: string;
  label: string;
}

export interface ChartSeries {
  key: string;
  label: string;
  points: ChartPoint[];
  /** SVG dash pattern, so series are distinguishable without colour. */
  dash?: string;
  color: string;
}

/**
 * Convert one stored decimal string to a plot coordinate.
 *
 * Returns null for anything that is not fixed-point or that would produce a
 * non-finite number, so a malformed value is skipped rather than poisoning
 * the axis range.
 */
export function toCoordinate(value: string): number | null {
  if (!isDecimalString(value)) return null;
  // The single permitted conversion: string -> number, for geometry only.
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Build a series from rows carrying a date and one decimal-string field. */
export function seriesFrom<T>(
  rows: readonly T[],
  options: {
    key: string;
    label: string;
    color: string;
    dash?: string;
    value: (row: T) => string;
    label_: (row: T) => string;
  },
): ChartSeries {
  const points: ChartPoint[] = [];
  rows.forEach((row, index) => {
    const source = options.value(row);
    const value = toCoordinate(source);
    if (value === null) return;
    points.push({ index, value, source, label: options.label_(row) });
  });
  return {
    key: options.key,
    label: options.label,
    color: options.color,
    dash: options.dash,
    points,
  };
}

/**
 * Rebase a series so its first plotted point sits at `base`.
 *
 * This is a coordinate transform, not a metric: every point keeps the exact
 * stored string it came from, and the stored return figures in
 * `result_metrics` are never touched. Returns null when there is nothing to
 * rebase against, or when the first point is zero and the ratio is undefined,
 * so an undefined comparison is dropped rather than drawn as a flat line.
 */
export function rebaseSeries(series: ChartSeries, base: number): ChartSeries | null {
  const first = series.points[0];
  if (first === undefined || first.value === 0) return null;
  return {
    ...series,
    points: series.points.map((point) => ({
      ...point,
      value: (point.value / first.value) * base,
    })),
  };
}

/** Marker glyphs are told apart by shape as well as colour. */
export type MarkerShape = "triangle-up" | "triangle-down";

export interface ChartMarker {
  index: number;
  value: number;
  /** The exact stored price this marker sits at. */
  source: string;
  label: string;
  /** How many identical persisted rows this one glyph stands for. */
  count: number;
}

export interface MarkerGroup {
  key: string;
  label: string;
  shape: MarkerShape;
  color: string;
  markers: ChartMarker[];
}

/**
 * Build one marker group from rows carrying an x position and a price.
 *
 * Rows whose x position or price is missing are skipped — the caller reports
 * how many, so nothing disappears silently. Rows that would land on exactly
 * the same pixel (same position, same stored price) collapse into a single
 * glyph carrying a count, which is what keeps a day with several identical
 * fills legible instead of overprinting.
 */
export function markersFrom<T>(
  rows: readonly T[],
  options: {
    key: string;
    label: string;
    shape: MarkerShape;
    color: string;
    index: (row: T) => number | null;
    value: (row: T) => string | null;
    label_: (row: T) => string;
  },
): { group: MarkerGroup; skipped: number } {
  const collapsed = new Map<string, ChartMarker>();
  let skipped = 0;

  for (const row of rows) {
    const index = options.index(row);
    const source = options.value(row);
    if (index === null || source === null) {
      skipped += 1;
      continue;
    }
    const value = toCoordinate(source);
    if (value === null) {
      skipped += 1;
      continue;
    }
    const identity = `${index}|${source}`;
    const existing = collapsed.get(identity);
    if (existing === undefined) {
      collapsed.set(identity, {
        index,
        value,
        source,
        label: options.label_(row),
        count: 1,
      });
    } else {
      existing.count += 1;
    }
  }

  return {
    group: {
      key: options.key,
      label: options.label,
      shape: options.shape,
      color: options.color,
      markers: [...collapsed.values()],
    },
    skipped,
  };
}

/** One stacked band of the activity chart; counts are indexed like the axis. */
export interface BarSeries {
  key: string;
  label: string;
  color: string;
  /** Adds a hatch overlay, so bands differ by texture as well as colour. */
  hatched?: boolean;
  counts: number[];
}

/**
 * Tally rows into per-position counts along an existing index axis.
 *
 * Whole rows only — nothing here touches a price, so no decimal is converted.
 */
export function countByIndex<T>(
  rows: readonly T[],
  length: number,
  index: (row: T) => number | null,
): number[] {
  const counts = new Array<number>(Math.max(0, length)).fill(0);
  for (const row of rows) {
    const position = index(row);
    if (position === null || position < 0 || position >= counts.length) continue;
    counts[position] += 1;
  }
  return counts;
}

export interface ChartRange {
  min: number;
  max: number;
  /** Total x positions; the widest series decides the axis. */
  count: number;
}

/**
 * The value range across every series plus any reference lines and markers.
 *
 * A flat series would give a zero-height range and divide by zero when
 * scaling, so it is padded to a visible band.
 */
export function chartRange(
  series: readonly ChartSeries[],
  references: readonly number[] = [],
  extras: readonly number[] = [],
): ChartRange | null {
  const values: number[] = [];
  let count = 0;
  for (const entry of series) {
    count = Math.max(count, entry.points.length);
    for (const point of entry.points) values.push(point.value);
  }
  for (const reference of references) values.push(reference);
  for (const extra of extras) values.push(extra);
  if (values.length === 0) return null;

  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) / 10;
    min -= pad;
    max += pad;
  }
  return { min, max, count };
}

/** Evenly spaced tick indices, for date labels along the x axis. */
export function tickIndices(count: number, desired = 5): number[] {
  if (count <= 0) return [];
  if (count === 1) return [0];
  const ticks = Math.min(desired, count);
  const step = (count - 1) / (ticks - 1);
  const indices: number[] = [];
  for (let i = 0; i < ticks; i += 1) indices.push(Math.round(i * step));
  return [...new Set(indices)];
}

/** Distinct, colour-blind-safe series colours; never the only differentiator. */
export const SERIES_COLORS = {
  strategy: "#1f4e79",
  benchmark1: "#c00000",
  benchmark2: "#2e7d32",
  drawdown: "#c00000",
  price: "#1f4e79",
  /** Trade sides. Shape and legend text carry the same distinction. */
  buy: "#1a7f37",
  sell: "#b3261e",
} as const;

/** Dash patterns pair with the colours so series remain distinguishable. */
export const SERIES_DASHES = {
  strategy: undefined,
  benchmark1: "6 3",
  benchmark2: "2 3",
} as const;
