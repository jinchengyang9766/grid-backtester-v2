"use client";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { LoadingState } from "@/components/ui/loading-state";
import { Table, TableScroll, Td, Th } from "@/components/ui/table";
import { CANONICAL_FIELDS, type DatasetDetail } from "@/lib/api/dataset-types";
import {
  EMPTY_VALUE,
  dataModeLabel,
  dateRangeLabel,
  displayText,
  humanizeCode,
  sourceTypeLabel,
  timestampLabel,
} from "@/lib/datasets/display";
import { FIELD_LABELS } from "@/lib/datasets/mapping";

/** Cleaning-summary keys rendered as named rows; anything else is forward-compatible. */
const SUMMARY_LABELS: Record<string, string> = {
  total_rows_parsed: "Total rows parsed",
  valid_rows: "Valid rows",
  bad_rows: "Bad rows",
  duplicate_dates: "Duplicate dates",
  final_row_count: "Final row count",
  data_mode: "Data mode",
};

function scalarText(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_VALUE;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export interface DatasetDetailPanelProps {
  open: boolean;
  loading: boolean;
  error: string | null;
  detail: DatasetDetail | null;
  /** Shown while the request is in flight, so the dialog has a name. */
  fallbackName: string;
  onClose: () => void;
  onRetry: () => void;
}

export function DatasetDetailPanel({
  open,
  loading,
  error,
  detail,
  fallbackName,
  onClose,
  onRetry,
}: DatasetDetailPanelProps) {
  const summary = detail?.cleaning_summary ?? {};
  const dateRange = summary.date_range as { start?: string; end?: string } | null | undefined;
  const badRowReasons = summary.bad_row_reasons as Record<string, number> | undefined;

  // Keys we do not render as named rows, kept for forward compatibility.
  const extraKeys = Object.keys(summary).filter(
    (key) => !(key in SUMMARY_LABELS) && key !== "date_range" && key !== "bad_row_reasons",
  );

  return (
    <Dialog
      open={open}
      title={detail ? detail.name : fallbackName}
      description="Dataset details, column mapping, and cleaning summary."
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      {loading && <LoadingState label="Loading dataset details…" />}

      {!loading && error && (
        <Alert
          tone="error"
          action={
            <Button variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {!loading && !error && detail && (
        <div className="space-y-6">
          <section>
            <h3 className="text-sm font-semibold">Summary</h3>
            <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              {(
                [
                  ["Dataset ID", String(detail.id)],
                  ["Security name", displayText(detail.security_name)],
                  ["Security code", displayText(detail.security_code)],
                  ["Source type", sourceTypeLabel(detail.source_type)],
                  ["Original filename", detail.original_filename],
                  ["Data mode", dataModeLabel(detail.data_mode)],
                  ["Date range", dateRangeLabel(detail.start_date, detail.end_date)],
                  ["Rows", String(detail.row_count)],
                  ["Created", timestampLabel(detail.created_at)],
                ] as [string, string][]
              ).map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3">
                  <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
                  <dd className="text-right font-medium break-words">{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section>
            <h3 className="text-sm font-semibold">Column mapping</h3>
            <div className="mt-2">
              <TableScroll label="Column mapping">
                <Table caption="Canonical field to source column mapping">
                  <thead>
                    <tr>
                      <Th>Field</Th>
                      <Th>Source column</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {CANONICAL_FIELDS.map((field) => (
                      <tr key={field}>
                        <Td>{FIELD_LABELS[field]}</Td>
                        <Td wrap>
                          {scalarText(detail.column_mapping[field]) === EMPTY_VALUE
                            ? "Not mapped"
                            : scalarText(detail.column_mapping[field])}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableScroll>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-semibold">Cleaning summary</h3>
            <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              {Object.entries(SUMMARY_LABELS).map(([key, label]) => (
                <div key={key} className="flex justify-between gap-3">
                  <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
                  <dd className="font-medium tabular-nums">
                    {key === "data_mode"
                      ? dataModeLabel(String(summary[key] ?? ""))
                      : scalarText(summary[key])}
                  </dd>
                </div>
              ))}
              <div className="flex justify-between gap-3">
                <dt className="text-slate-600 dark:text-slate-400">Date range</dt>
                <dd className="font-medium">
                  {dateRangeLabel(dateRange?.start, dateRange?.end)}
                </dd>
              </div>
            </dl>

            {badRowReasons && Object.keys(badRowReasons).length > 0 && (
              <div className="mt-3">
                <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Rejected-row reasons
                </h4>
                <TableScroll label="Rejected-row reason counts">
                  <Table caption="Count of rejected rows by reason">
                    <thead>
                      <tr>
                        <Th>Reason</Th>
                        <Th numeric>Rows</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(badRowReasons).map(([reason, count]) => (
                        <tr key={reason}>
                          <Td wrap>{humanizeCode(reason)}</Td>
                          <Td numeric>{count}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableScroll>
              </div>
            )}

            {extraKeys.length > 0 && (
              <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
                {extraKeys.map((key) => (
                  <div key={key} className="flex justify-between gap-3">
                    <dt className="text-slate-600 dark:text-slate-400">{humanizeCode(key)}</dt>
                    <dd className="font-medium break-words">{scalarText(summary[key])}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}
