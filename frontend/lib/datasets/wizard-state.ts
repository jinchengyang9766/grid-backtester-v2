/**
 * Upload-wizard state machine (SPEC Section 28), Task 21 scope only:
 *
 *     UPLOAD -> DETECTING -> MAPPING -> CLEANING_REVIEW -> PREVIEW
 *            -> DATASET_SAVED
 *
 * STRATEGY_CONFIG, RUNNING, and DONE belong to a later task and are
 * deliberately absent.
 *
 * The invariant this module protects: the held `preview_token` is always
 * bound to exactly one File and one mapping (SPEC Section 25.2). Selecting a
 * different File, or editing the mapping, must invalidate or replace the
 * token before anything can be saved.
 */

import type { DatasetPreview, ManualColumnMapping } from "@/lib/api/dataset-types";

export const WIZARD_STEPS = [
  "UPLOAD",
  "DETECTING",
  "MAPPING",
  "CLEANING_REVIEW",
  "PREVIEW",
  "DATASET_SAVED",
] as const;

export type WizardStep = (typeof WIZARD_STEPS)[number];

/** Steps shown in the progress indicator (DETECTING is a transient state). */
export const VISIBLE_STEPS = [
  { step: "UPLOAD", label: "Upload" },
  { step: "MAPPING", label: "Columns" },
  { step: "CLEANING_REVIEW", label: "Cleaning" },
  { step: "PREVIEW", label: "Preview & save" },
  { step: "DATASET_SAVED", label: "Saved" },
] as const satisfies readonly { step: WizardStep; label: string }[];

export function visibleStepIndex(step: WizardStep): number {
  // DETECTING has no tile of its own; it belongs to the Upload stage.
  const effective: WizardStep = step === "DETECTING" ? "UPLOAD" : step;
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
