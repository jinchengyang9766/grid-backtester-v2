/**
 * Upload-wizard state machine (SPEC Section 28):
 *
 *     UPLOAD -> DETECTING -> MAPPING -> CLEANING_REVIEW -> PREVIEW
 *            -> DATASET_SAVED -> STRATEGY_CONFIG -> RUNNING -> DONE
 *
 * The invariant the dataset half protects: the held `preview_token` is always
 * bound to exactly one File and one mapping (SPEC Section 25.2). Selecting a
 * different File, or editing the mapping, must invalidate or replace the
 * token before anything can be saved.
 *
 * From DATASET_SAVED onwards only the dataset *id* matters — the strategy half
 * needs neither the original File nor the preview token, so a reload with
 * `?dataset_id=` resumes cleanly.
 */

import type { DatasetPreview, ManualColumnMapping } from "@/lib/api/dataset-types";

export const WIZARD_STEPS = [
  "UPLOAD",
  "DETECTING",
  "MAPPING",
  "CLEANING_REVIEW",
  "PREVIEW",
  "DATASET_SAVED",
  "STRATEGY_CONFIG",
  "RUNNING",
  "DONE",
] as const;

export type WizardStep = (typeof WIZARD_STEPS)[number];

/** Steps shown in the progress indicator (DETECTING/RUNNING are transient). */
export const VISIBLE_STEPS = [
  { step: "UPLOAD", label: "Upload" },
  { step: "MAPPING", label: "Columns" },
  { step: "CLEANING_REVIEW", label: "Cleaning" },
  { step: "PREVIEW", label: "Preview & save" },
  { step: "DATASET_SAVED", label: "Saved" },
  { step: "STRATEGY_CONFIG", label: "Strategy" },
  { step: "DONE", label: "Result" },
] as const satisfies readonly { step: WizardStep; label: string }[];

export function visibleStepIndex(step: WizardStep): number {
  // DETECTING belongs to Upload; RUNNING belongs to Strategy.
  const effective: WizardStep =
    step === "DETECTING" ? "UPLOAD" : step === "RUNNING" ? "STRATEGY_CONFIG" : step;
  return VISIBLE_STEPS.findIndex((entry) => entry.step === effective);
}

/**
 * The preview response currently held, together with the exact mapping that
 * produced it. Keeping them in one object makes it impossible to hold a token
 * whose mapping is unknown.
 */
export interface HeldPreview {
  preview: DatasetPreview;
  /** The complete mapping the token is bound to. */
  mapping: ManualColumnMapping;
}

/** The saved-dataset handoff Task 22 will pick up from. */
export interface SavedDatasetHandoff {
  id: number;
  name: string;
  data_mode: string;
  start_date: string;
  end_date: string;
  row_count: number;
}
