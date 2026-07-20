"use client";

/**
 * Upload wizard orchestrator (SPEC Section 28), Task 21 scope:
 * UPLOAD → DETECTING → MAPPING → CLEANING_REVIEW → PREVIEW → DATASET_SAVED.
 *
 * Two invariants drive the whole component:
 *
 * 1. The selected File lives only in component state. It is never written to
 *    localStorage, sessionStorage, IndexedDB, or any cache — a re-mapping
 *    needs the original bytes again, and holding them in memory is the only
 *    place they belong.
 * 2. A `preview_token` is valid for exactly one (file, mapping) pair. Any
 *    change to either must abandon or replace the token before a save, so the
 *    rows that get persisted are always the rows the user reviewed.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CleaningReviewStep } from "@/components/upload/cleaning-review-step";
import { CleanedPreviewStep } from "@/components/upload/cleaned-preview-step";
import { DatasetSavedStep } from "@/components/upload/dataset-saved-step";
import { MappingStep } from "@/components/upload/mapping-step";
import { UploadStep } from "@/components/upload/upload-step";
import { WizardProgress } from "@/components/upload/wizard-progress";
import { previewDataset, saveDataset } from "@/lib/api/datasets";
import {
  PREVIEW_TOKEN_NOT_FOUND,
  type CanonicalField,
  type DatasetPreview,
  type ManualColumnMapping,
} from "@/lib/api/dataset-types";
import { ApiClientError } from "@/lib/api/errors";
import { hasAcceptedExtension, suggestDatasetName } from "@/lib/datasets/display";
import { sameMapping, toManualMapping } from "@/lib/datasets/mapping";
import type {
  HeldPreview,
  SavedDatasetHandoff,
  WizardStep,
} from "@/lib/datasets/wizard-state";

const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(error: unknown): string {
  return error instanceof ApiClientError ? error.message : GENERIC_FAILURE;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function DatasetUploadWizard({
  initialSaved,
}: {
  /** Present when arriving at /backtest/new?dataset_id=… */
  initialSaved?: SavedDatasetHandoff;
}) {
  const router = useRouter();

  const [step, setStep] = useState<WizardStep>(initialSaved ? "DATASET_SAVED" : "UPLOAD");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  /** The preview response plus the exact mapping its token is bound to. */
  const [held, setHeld] = useState<HeldPreview | null>(null);
  /** The mapping currently shown in the selectors, which may differ. */
  const [mapping, setMapping] = useState<ManualColumnMapping | null>(null);

  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [tokenExpired, setTokenExpired] = useState(false);

  const [previewPending, setPreviewPending] = useState(false);
  const [savePending, setSavePending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [saved, setSaved] = useState<SavedDatasetHandoff | null>(initialSaved ?? null);

  // Only the newest preview may publish its result; an older in-flight
  // response for a previous file or mapping is discarded.
  const previewGeneration = useRef(0);
  const previewController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      previewController.current?.abort();
    };
  }, []);

  const runPreview = useCallback(
    async (
      target: File,
      manualMapping: ManualColumnMapping | undefined,
      options: { onSuccess: (preview: DatasetPreview) => void; onFailure: () => void },
    ) => {
      previewController.current?.abort();
      const controller = new AbortController();
      previewController.current = controller;
      const generation = ++previewGeneration.current;

      try {
        const preview = await previewDataset(target, manualMapping, controller.signal);
        if (!mounted.current || generation !== previewGeneration.current) return;
        // Response and token are adopted together, never separately.
        setHeld({
          preview,
          mapping: manualMapping ?? toManualMapping(preview.column_mapping_used),
        });
        setMapping(toManualMapping(preview.column_mapping_used));
        options.onSuccess(preview);
      } catch (error) {
        if (isAbort(error)) return;
        if (!mounted.current || generation !== previewGeneration.current) return;
        setRequestError(messageOf(error));
        options.onFailure();
      } finally {
        if (mounted.current && generation === previewGeneration.current) {
          setPreviewPending(false);
          setRefreshing(false);
        }
      }
    },
    [],
  );

  /** Selecting a different file invalidates everything derived from the old one. */
  const handleSelectFile = useCallback((next: File | null) => {
    previewController.current?.abort();
    previewGeneration.current += 1;

    setFile(next);
    setFileError(null);
    setRequestError(null);
    setHeld(null);
    setMapping(null);
    setName("");
    setNameError(null);
    setSaveError(null);
    setTokenExpired(false);
    setPreviewPending(false);
    setStep("UPLOAD");
  }, []);

  const handleDetect = useCallback(() => {
    if (previewPending) return;
    if (file === null) {
      setFileError("Choose a file to preview.");
      return;
    }
    if (!hasAcceptedExtension(file.name)) {
      setFileError("Choose a .xls (TongdaXin text export) or .csv file.");
      return;
    }
    setFileError(null);
    setRequestError(null);
    setPreviewPending(true);
    setStep("DETECTING");

    void runPreview(file, undefined, {
      onSuccess: (preview) => {
        setName(
          suggestDatasetName(preview.security_name, preview.security_code, file.name),
        );
        setStep("MAPPING");
      },
      onFailure: () => setStep("UPLOAD"),
    });
  }, [file, previewPending, runPreview]);

  const handleMappingChange = useCallback(
    (field: CanonicalField, source: string | null) => {
      setMapping((current) => (current === null ? current : { ...current, [field]: source }));
    },
    [],
  );

  const handleMappingReset = useCallback(() => {
    // Snap back to the mapping the held token is bound to.
    if (held) setMapping({ ...held.mapping });
  }, [held]);

  const handleMappingContinue = useCallback(() => {
    if (previewPending || held === null || mapping === null || file === null) return;

    if (sameMapping(mapping, held.mapping)) {
      // Unchanged: the held token already describes this exact mapping.
      setRequestError(null);
      setStep("CLEANING_REVIEW");
      return;
    }

    setRequestError(null);
    setPreviewPending(true);
    void runPreview(file, mapping, {
      onSuccess: () => setStep("CLEANING_REVIEW"),
      // Stay on MAPPING with the edited controls intact; the previous token
      // remains held but is never used while the shown mapping differs.
      onFailure: () => setStep("MAPPING"),
    });
  }, [file, held, mapping, previewPending, runPreview]);

  const handleRefreshPreview = useCallback(() => {
    if (refreshing || file === null || mapping === null) return;
    setRefreshing(true);
    setSaveError(null);
    setRequestError(null);
    void runPreview(file, mapping, {
      onSuccess: () => setTokenExpired(false),
      onFailure: () => undefined,
    });
  }, [file, mapping, refreshing, runPreview]);

  const handleSave = useCallback(async () => {
    if (savePending || held === null) return;

    const trimmed = name.trim();
    if (trimmed === "") {
      setNameError("Enter a name for this dataset.");
      return;
    }
    setNameError(null);
    setSaveError(null);
    setSavePending(true);

    try {
      const result = await saveDataset({
        name: trimmed,
        preview_token: held.preview.preview_token,
      });
      if (!mounted.current) return;
      setSaved(result);
      setStep("DATASET_SAVED");
      // Only the id travels in the URL — never the token or the mapping.
      router.replace(`/backtest/new?dataset_id=${result.id}`);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiClientError && error.code === PREVIEW_TOKEN_NOT_FOUND) {
        // Offer a refresh instead of silently retrying with a dead token.
        setTokenExpired(true);
        setSaveError(error.message);
      } else {
        setSaveError(messageOf(error));
      }
    } finally {
      if (mounted.current) setSavePending(false);
    }
  }, [held, name, router, savePending]);

  if (step === "DATASET_SAVED" && saved) {
    return (
      <>
        <WizardProgress step="DATASET_SAVED" />
        <DatasetSavedStep
          dataset={saved}
          // The strategy half needs only the id, so hand off through the URL:
          // a reload then resumes without the File or the preview token.
          onConfigureStrategy={() =>
            router.replace(`/backtest/new?dataset_id=${saved.id}&configure=1`)
          }
        />
      </>
    );
  }

  return (
    <>
      <WizardProgress step={step} />

      {(step === "UPLOAD" || step === "DETECTING") && (
        <UploadStep
          file={file}
          fileError={fileError}
          requestError={requestError}
          pending={previewPending}
          onSelectFile={handleSelectFile}
          onSubmit={handleDetect}
        />
      )}

      {step === "MAPPING" && held && mapping && (
        <MappingStep
          preview={held.preview}
          tokenMapping={held.mapping}
          mapping={mapping}
          pending={previewPending}
          error={requestError}
          onChange={handleMappingChange}
          onReset={handleMappingReset}
          onContinue={handleMappingContinue}
          onBack={() => setStep("UPLOAD")}
        />
      )}

      {step === "CLEANING_REVIEW" && held && (
        <CleaningReviewStep
          preview={held.preview}
          onContinue={() => setStep("PREVIEW")}
          onBack={() => setStep("MAPPING")}
        />
      )}

      {step === "PREVIEW" && held && (
        <CleanedPreviewStep
          preview={held.preview}
          name={name}
          nameError={nameError}
          saveError={saveError}
          tokenExpired={tokenExpired}
          pending={savePending}
          refreshing={refreshing}
          onNameChange={setName}
          onSave={() => void handleSave()}
          onRefreshPreview={handleRefreshPreview}
          onBack={() => setStep("MAPPING")}
        />
      )}
    </>
  );
}
