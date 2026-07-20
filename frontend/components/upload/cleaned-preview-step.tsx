"use client";

import { useId } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Table, TableScroll, Td, Th } from "@/components/ui/table";
import type { DatasetPreview } from "@/lib/api/dataset-types";
import { EMPTY_VALUE, dataModeLabel, dateRangeLabel } from "@/lib/datasets/display";

export interface CleanedPreviewStepProps {
  preview: DatasetPreview;
  name: string;
  nameError: string | null;
  saveError: string | null;
  /** Set when the token expired or was consumed, offering a refresh instead. */
  tokenExpired: boolean;
  pending: boolean;
  refreshing: boolean;
  onNameChange: (value: string) => void;
  onSave: () => void;
  onRefreshPreview: () => void;
  onBack: () => void;
}

/** Decimal strings are rendered verbatim; null becomes a neutral dash. */
function cell(value: string | null) {
  return value === null || value === "" ? EMPTY_VALUE : value;
}

export function CleanedPreviewStep({
  preview,
  name,
  nameError,
  saveError,
  tokenExpired,
  pending,
  refreshing,
  onNameChange,
  onSave,
  onRefreshPreview,
  onBack,
}: CleanedPreviewStepProps) {
  const nameId = useId();
  const summary = preview.cleaning_summary;
  const showsSample = preview.preview_rows.length < summary.final_row_count;

  return (
    <section aria-labelledby="preview-heading" className="space-y-5">
      <div>
        <h2 id="preview-heading" className="text-lg font-semibold">
          Preview cleaned data and save
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          These are the rows that will be stored.
        </p>
      </div>

      <dl className="grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Rows to be saved</dt>
          <dd className="font-medium tabular-nums">{summary.final_row_count}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Rows shown below</dt>
          <dd className="font-medium tabular-nums">{preview.preview_rows.length}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Date range</dt>
          <dd className="font-medium">
            {dateRangeLabel(summary.date_range?.start, summary.date_range?.end)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-600 dark:text-slate-400">Data mode</dt>
          <dd className="font-medium">{dataModeLabel(summary.data_mode)}</dd>
        </div>
      </dl>

      {showsSample && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          This dataset is large, so the server returns a bounded sample — the
          first and last rows — rather than all {summary.final_row_count} rows.
          Every row is still saved.
        </p>
      )}

      <TableScroll label="Cleaned data preview">
        <Table caption="Cleaned rows that will be saved with this dataset">
          <thead>
            <tr>
              <Th>Date</Th>
              <Th numeric>Open</Th>
              <Th numeric>High</Th>
              <Th numeric>Low</Th>
              <Th numeric>Close</Th>
              <Th numeric>Volume</Th>
            </tr>
          </thead>
          <tbody>
            {preview.preview_rows.map((row) => (
              <tr key={row.date}>
                <Td>{row.date}</Td>
                <Td numeric>{cell(row.open)}</Td>
                <Td numeric>{cell(row.high)}</Td>
                <Td numeric>{cell(row.low)}</Td>
                <Td numeric>{row.close}</Td>
                <Td numeric>{cell(row.volume)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>

      {tokenExpired ? (
        <Alert
          tone="error"
          title="This preview is no longer available"
          action={
            <Button
              variant="secondary"
              onClick={onRefreshPreview}
              pending={refreshing}
              pendingLabel="Refreshing…"
            >
              Refresh preview
            </Button>
          }
        >
          The preview expired or was already used. Refresh it with the file and
          mapping you already selected, then save again.
        </Alert>
      ) : (
        saveError && <Alert tone="error">{saveError}</Alert>
      )}

      <FormField
        id={nameId}
        label="Dataset name"
        description="Used to identify this dataset when configuring a backtest."
        error={nameError ?? undefined}
      >
        {(aria) => (
          <Input
            {...aria}
            name="name"
            value={name}
            invalid={Boolean(nameError)}
            onChange={(event) => onNameChange(event.target.value)}
          />
        )}
      </FormField>

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={onSave}
          pending={pending}
          pendingLabel="Saving…"
          disabled={tokenExpired || refreshing}
        >
          Save dataset
        </Button>
        <Button variant="ghost" onClick={onBack} disabled={pending || refreshing}>
          Back to column mapping
        </Button>
      </div>
    </section>
  );
}
