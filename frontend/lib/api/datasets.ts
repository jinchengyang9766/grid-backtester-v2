/**
 * Dataset API functions (SPEC Section 25.2).
 *
 * Preview is `multipart/form-data`; save is JSON carrying only `name` and
 * `preview_token`. The selected File is passed straight into a FormData body
 * and is never copied anywhere persistent, and the preview token is only ever
 * a request field — it is never logged or placed in a URL.
 */

import { apiPostJson, apiRequest } from "./client";
import type {
  DatasetDetail,
  DatasetListResponse,
  DatasetPreview,
  DatasetSaveInput,
  DatasetSaved,
  ManualColumnMapping,
} from "./dataset-types";

/**
 * Upload one file for parsing, mapping, and cleaning.
 *
 * `manual_mapping` is appended as a **single JSON string field**, not one
 * multipart field per entry — the backend reads it with `Form()` and parses
 * it itself. Content-Type is deliberately left unset so the browser generates
 * the multipart boundary; setting it by hand would omit the boundary and make
 * the body unparseable.
 */
export function previewDataset(
  file: File,
  manualMapping?: ManualColumnMapping,
  signal?: AbortSignal,
): Promise<DatasetPreview> {
  const body = new FormData();
  body.append("file", file);
  if (manualMapping !== undefined) {
    body.append("manual_mapping", JSON.stringify(manualMapping));
  }
  return apiRequest<DatasetPreview>("/api/datasets/preview", {
    method: "POST",
    body,
    signal,
  });
}

/** Persist the cleaned rows already bound to the token. */
export function saveDataset(
  input: DatasetSaveInput,
  signal?: AbortSignal,
): Promise<DatasetSaved> {
  // Exactly two fields: the backend forbids extras, and the mapping is
  // already baked into the token's cache entry.
  return apiPostJson<DatasetSaved>(
    "/api/datasets",
    { name: input.name, preview_token: input.preview_token },
    { signal },
  );
}

export function listDatasets(signal?: AbortSignal): Promise<DatasetListResponse> {
  return apiRequest<DatasetListResponse>("/api/datasets", { method: "GET", signal });
}

export function getDataset(
  datasetId: number,
  signal?: AbortSignal,
): Promise<DatasetDetail> {
  return apiRequest<DatasetDetail>(`/api/datasets/${datasetId}`, {
    method: "GET",
    signal,
  });
}

/** Returns 204; the caller removes the row only after that confirmation. */
export function deleteDataset(datasetId: number, signal?: AbortSignal): Promise<void> {
  return apiRequest<void>(`/api/datasets/${datasetId}`, { method: "DELETE", signal });
}
