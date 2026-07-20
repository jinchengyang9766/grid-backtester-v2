/**
 * Dataset request/response contracts (SPEC Section 25.2).
 *
 * These mirror the checked-in backend Pydantic schemas in
 * `backend/app/api/schemas/datasets.py` field for field. Where SPEC 25.2's
 * illustrative JSON is older than the implemented schema — notably
 * `duplicate_rows`, which SPEC sketches as `{ kept, discarded }` but the
 * backend actually returns as `{ kept_row_number, discarded_row_number,
 * kept_raw, discarded_raw, reason }` — the implemented schema wins.
 *
 * Every Decimal arrives as a string and stays a string; nothing here is ever
 * parsed into a float.
 */

/** The six canonical fields the importing pipeline recognises. */
export const CANONICAL_FIELDS = [
  "date",
  "open",
  "high",
  "low",
  "close",
  "volume",
] as const;

export type CanonicalField = (typeof CANONICAL_FIELDS)[number];

/** Date and Close are always required (SPEC Section 2.2). */
export const REQUIRED_FIELDS = ["date", "close"] as const satisfies readonly CanonicalField[];

/** Open/High/Low must be mapped together or not at all. */
export const OHLC_FIELDS = ["open", "high", "low"] as const satisfies readonly CanonicalField[];

/**
 * Canonical field -> source column header. The backend echoes only mapped
 * fields, so a missing key means "unmapped"; an explicit `null` sent back in
 * `manual_mapping` is what *unmaps* an auto-detected field.
 */
export type ColumnMapping = Partial<Record<CanonicalField, string>>;

/** What the client sends: every field stated, `null` meaning "not mapped". */
export type ManualColumnMapping = Record<CanonicalField, string | null>;

export interface PreviewBar {
  date: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string;
  volume: string | null;
}

export interface BadRow {
  row_number: number;
  reason: string;
  raw: Record<string, string>;
}

export interface DuplicateRow {
  date: string;
  kept_row_number: number;
  discarded_row_number: number;
  kept_raw: Record<string, string>;
  discarded_raw: Record<string, string>;
  reason: string;
}

export interface DateRange {
  start: string;
  end: string;
}

export interface CleaningSummary {
  total_rows_parsed: number;
  valid_rows: number;
  bad_rows: number;
  duplicate_dates: number;
  final_row_count: number;
  date_range: DateRange | null;
  data_mode: string;
  bad_row_reasons: Record<string, number>;
}

/** `POST /api/datasets/preview` → 200. */
export interface DatasetPreview {
  detected_format: string;
  detected_encoding: string;
  auto_column_mapping: ColumnMapping;
  column_mapping_used: ColumnMapping;
  security_name: string | null;
  security_code: string | null;
  data_mode: string;
  preview_rows: PreviewBar[];
  bad_rows: BadRow[];
  duplicate_rows: DuplicateRow[];
  cleaning_summary: CleaningSummary;
  /** Opaque and short-lived; never rendered, logged, or put in a URL. */
  preview_token: string;
}

export interface DatasetSaveInput {
  name: string;
  preview_token: string;
}

/** `POST /api/datasets` → 201. */
export interface DatasetSaved {
  id: number;
  name: string;
  data_mode: string;
  start_date: string;
  end_date: string;
  row_count: number;
  created_at: string;
}

/** One `GET /api/datasets` item — metadata only, never user_id or bars. */
export interface DatasetSummary {
  id: number;
  name: string;
  source_type: string;
  original_filename: string;
  security_name: string | null;
  security_code: string | null;
  data_mode: string;
  start_date: string;
  end_date: string;
  row_count: number;
  created_at: string;
}

export interface DatasetListResponse {
  items: DatasetSummary[];
}

/** `GET /api/datasets/{id}` — summary plus the stored JSON columns. */
export interface DatasetDetail extends DatasetSummary {
  column_mapping: Record<string, unknown>;
  cleaning_summary: Record<string, unknown>;
}

/** Backend error codes this feature branches on. */
export const UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE";
export const ENCODING_DETECTION_FAILED = "ENCODING_DETECTION_FAILED";
export const HEADER_NOT_FOUND = "HEADER_NOT_FOUND";
export const MISSING_REQUIRED_COLUMN = "MISSING_REQUIRED_COLUMN";
export const PREVIEW_TOKEN_NOT_FOUND = "PREVIEW_TOKEN_NOT_FOUND";
export const DATASET_NOT_FOUND = "DATASET_NOT_FOUND";
export const DATASET_IN_USE = "DATASET_IN_USE";
