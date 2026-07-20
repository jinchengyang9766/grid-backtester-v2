/**
 * Column-mapping helpers for the wizard's MAPPING step.
 *
 * These only validate and compare mappings. No parsing, cleaning, or row
 * interpretation happens in the browser — the backend owns that entirely, and
 * a second implementation here could disagree with the cleaned rows a token is
 * bound to.
 */

import {
  CANONICAL_FIELDS,
  OHLC_FIELDS,
  REQUIRED_FIELDS,
  type CanonicalField,
  type ColumnMapping,
  type ManualColumnMapping,
} from "@/lib/api/dataset-types";

export const FIELD_LABELS: Record<CanonicalField, string> = {
  date: "Date",
  open: "Open",
  high: "High",
  low: "Low",
  close: "Close",
  volume: "Volume",
};

/** Sentinel for "not mapped" in a <select>, since a value of "" is falsy. */
export const UNMAPPED = "__unmapped__";

/** Expand the backend's sparse mapping into an explicit all-fields form. */
export function toManualMapping(mapping: ColumnMapping): ManualColumnMapping {
  const complete = {} as ManualColumnMapping;
  for (const field of CANONICAL_FIELDS) {
    complete[field] = mapping[field] ?? null;
  }
  return complete;
}

/** True when two mappings select the same source column for every field. */
export function sameMapping(a: ManualColumnMapping, b: ManualColumnMapping): boolean {
  return CANONICAL_FIELDS.every((field) => a[field] === b[field]);
}

export interface MappingValidation {
  valid: boolean;
  /** Field-scoped messages, keyed by canonical field. */
  fieldErrors: Partial<Record<CanonicalField, string>>;
  /** Problems that span fields, e.g. one column used twice. */
  formErrors: string[];
}

/**
 * Mirror of the backend's own rules (SPEC Sections 2.2, 6) so the user gets
 * immediate feedback; the backend still enforces them authoritatively.
 */
export function validateMapping(mapping: ManualColumnMapping): MappingValidation {
  const fieldErrors: Partial<Record<CanonicalField, string>> = {};
  const formErrors: string[] = [];

  for (const field of REQUIRED_FIELDS) {
    if (mapping[field] === null) {
      fieldErrors[field] = `${FIELD_LABELS[field]} must be mapped.`;
    }
  }

  const mappedOhlc = OHLC_FIELDS.filter((field) => mapping[field] !== null);
  if (mappedOhlc.length > 0 && mappedOhlc.length < OHLC_FIELDS.length) {
    const missing = OHLC_FIELDS.filter((field) => mapping[field] === null);
    for (const field of missing) {
      fieldErrors[field] =
        `${FIELD_LABELS[field]} is required when any of Open/High/Low is mapped.`;
    }
    formErrors.push(
      "Open, High, and Low must be mapped together, or all left unmapped for a close-only dataset.",
    );
  }

  // One source column must never feed two canonical fields.
  const seen = new Map<string, CanonicalField>();
  for (const field of CANONICAL_FIELDS) {
    const source = mapping[field];
    if (source === null) continue;
    const previous = seen.get(source);
    if (previous !== undefined) {
      const message = `Column "${source}" is already mapped to ${FIELD_LABELS[previous]}.`;
      fieldErrors[field] = message;
      formErrors.push(message);
    } else {
      seen.set(source, field);
    }
  }

  return {
    valid: Object.keys(fieldErrors).length === 0 && formErrors.length === 0,
    fieldErrors,
    formErrors,
  };
}

/**
 * The data mode the mapping implies. Shown as a hint only; the authoritative
 * value always comes from the preview response.
 */
export function impliedDataMode(mapping: ManualColumnMapping): "OHLCV" | "CLOSE_ONLY" {
  return OHLC_FIELDS.every((field) => mapping[field] !== null) ? "OHLCV" : "CLOSE_ONLY";
}

/**
 * Source columns offered in the selectors.
 *
 * Built strictly from headers the backend actually reported, so no column
 * name is ever invented: the values of the auto-detected and currently-used
 * mappings, plus the keys of any returned raw rows (`bad_rows[].raw` and the
 * duplicate rows' raw maps are keyed by the file's own headers, so they
 * expose columns that no field currently maps to).
 *
 * The preview response carries no standalone header list, so a file whose
 * every row is clean offers only its already-mapped columns. The UI says so
 * rather than pretending the list is exhaustive.
 */
export function sourceColumnOptions(preview: {
  auto_column_mapping: ColumnMapping;
  column_mapping_used: ColumnMapping;
  bad_rows?: { raw: Record<string, string> }[];
  duplicate_rows?: {
    kept_raw: Record<string, string>;
    discarded_raw: Record<string, string>;
  }[];
}): string[] {
  const columns = new Set<string>();

  for (const mapping of [preview.auto_column_mapping, preview.column_mapping_used]) {
    for (const value of Object.values(mapping)) {
      if (typeof value === "string" && value !== "") columns.add(value);
    }
  }
  for (const badRow of preview.bad_rows ?? []) {
    for (const header of Object.keys(badRow.raw)) columns.add(header);
  }
  for (const duplicate of preview.duplicate_rows ?? []) {
    for (const header of Object.keys(duplicate.kept_raw)) columns.add(header);
    for (const header of Object.keys(duplicate.discarded_raw)) columns.add(header);
  }

  return [...columns].sort((a, b) => a.localeCompare(b));
}
