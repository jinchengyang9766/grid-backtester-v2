"use client";

import { useId } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import {
  CANONICAL_FIELDS,
  type CanonicalField,
  type DatasetPreview,
  type ManualColumnMapping,
} from "@/lib/api/dataset-types";
import { dataModeLabel, displayText } from "@/lib/datasets/display";
import {
  FIELD_LABELS,
  UNMAPPED,
  impliedDataMode,
  sameMapping,
  sourceColumnOptions,
  validateMapping,
} from "@/lib/datasets/mapping";

export interface MappingStepProps {
  preview: DatasetPreview;
  /** The mapping the currently-held preview_token is bound to. */
  tokenMapping: ManualColumnMapping;
  mapping: ManualColumnMapping;
  pending: boolean;
  error: string | null;
  onChange: (field: CanonicalField, source: string | null) => void;
  onReset: () => void;
  onContinue: () => void;
  onBack: () => void;
}

export function MappingStep({
  preview,
  tokenMapping,
  mapping,
  pending,
  error,
  onChange,
  onReset,
  onContinue,
  onBack,
}: MappingStepProps) {
  const baseId = useId();
  const validation = validateMapping(mapping);
  const edited = !sameMapping(mapping, tokenMapping);
  const columns = sourceColumnOptions(preview);

  return (
    <section aria-labelledby="mapping-heading" className="space-y-5">
      <div>
        <h2 id="mapping-heading" className="text-lg font-semibold">
          Confirm column mapping
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          These columns were detected in your file. Adjust them if anything was
          matched incorrectly.
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <dl className="grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Detected format</dt>
          <dd className="font-medium">{preview.detected_format}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Detected encoding</dt>
          <dd className="font-medium">{preview.detected_encoding}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Security name</dt>
          <dd className="font-medium break-words">{displayText(preview.security_name)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Security code</dt>
          <dd className="font-medium">{displayText(preview.security_code)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Data mode</dt>
          <dd className="font-medium">{dataModeLabel(preview.data_mode)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Rows parsed</dt>
          <dd className="font-medium tabular-nums">
            {preview.cleaning_summary.total_rows_parsed}
          </dd>
        </div>
      </dl>

      <div>
        <p className="text-sm">
          {edited ? (
            <Badge tone="warning">Mapping edited — data will be re-read</Badge>
          ) : (
            <Badge tone="info">Automatically detected mapping</Badge>
          )}
        </p>
        {edited && (
          <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-400">
            Changing a column changes which rows are valid, so the file is sent
            again for re-parsing before you continue.
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {CANONICAL_FIELDS.map((field) => {
          const id = `${baseId}-${field}`;
          const value = mapping[field];
          const isRequired = field === "date" || field === "close";
          return (
            <FormField
              key={field}
              id={id}
              label={`${FIELD_LABELS[field]}${isRequired ? " (required)" : ""}`}
              error={validation.fieldErrors[field]}
            >
              {(aria) => (
                <select
                  {...aria}
                  name={field}
                  value={value ?? UNMAPPED}
                  aria-invalid={validation.fieldErrors[field] ? true : undefined}
                  onChange={(event) =>
                    onChange(
                      field,
                      event.target.value === UNMAPPED ? null : event.target.value,
                    )
                  }
                  className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-900"
                >
                  <option value={UNMAPPED}>Not mapped</option>
                  {columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
          );
        })}
      </div>

      {validation.formErrors.length > 0 && (
        <Alert tone="error" title="Fix the mapping to continue">
          <ul className="list-inside list-disc">
            {[...new Set(validation.formErrors)].map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Alert>
      )}

      <p className="text-xs text-slate-600 dark:text-slate-400">
        With this mapping the dataset would be read as{" "}
        <span className="font-medium">{dataModeLabel(impliedDataMode(mapping))}</span>. Only
        columns the server recognised in your file can be selected.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={onContinue}
          pending={pending}
          pendingLabel="Re-reading file…"
          disabled={!validation.valid}
        >
          {edited ? "Apply mapping and continue" : "Continue"}
        </Button>
        {edited && (
          <Button variant="secondary" onClick={onReset} disabled={pending}>
            Undo changes
          </Button>
        )}
        <Button variant="ghost" onClick={onBack} disabled={pending}>
          Back to upload
        </Button>
      </div>
    </section>
  );
}
