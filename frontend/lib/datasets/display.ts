/**
 * Presentation helpers for Dataset metadata.
 *
 * These only relabel and format values the backend already produced. Nothing
 * here recomputes a count, reinterprets a row, or converts a Decimal string
 * into a number.
 */

/** Shown in place of a null/absent value, never an empty cell. */
export const EMPTY_VALUE = "—";

export function displayText(value: string | null | undefined): string {
  return value === null || value === undefined || value === "" ? EMPTY_VALUE : value;
}

const DATA_MODE_LABELS: Record<string, string> = {
  OHLCV: "OHLCV (open, high, low, close, volume)",
  CLOSE_ONLY: "Close only",
};

export function dataModeLabel(mode: string): string {
  return DATA_MODE_LABELS[mode] ?? mode;
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  TDX_XLS: "TongdaXin text export (.xls)",
  CSV: "CSV",
};

export function sourceTypeLabel(sourceType: string): string {
  return SOURCE_TYPE_LABELS[sourceType] ?? sourceType;
}

/** Turn `NON_POSITIVE_PRICE` into `Non positive price` for display. */
export function humanizeCode(code: string): string {
  const spaced = code.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function dateRangeLabel(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start || !end) return EMPTY_VALUE;
  return `${start} to ${end}`;
}

/** A locale-independent, hydration-safe rendering of an ISO timestamp. */
export function timestampLabel(value: string): string {
  // Server and client must agree, so no locale formatting is used here.
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
  return match ? `${match[1]} ${match[2]}` : value;
}

export function fileSizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Accepted upload extensions (SPEC Section 2.1). */
export const ACCEPTED_EXTENSIONS = [".xls", ".csv"] as const;

export function hasAcceptedExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/** A sensible default Dataset name, still fully editable by the user. */
export function suggestDatasetName(
  securityName: string | null,
  securityCode: string | null,
  filename: string,
): string {
  if (securityName && securityCode) return `${securityName} ${securityCode}`;
  if (securityName) return securityName;
  if (securityCode) return securityCode;
  const stem = filename.replace(/\.[^.]+$/, "").trim();
  return stem || "Dataset";
}
