"use client";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableScroll, Td, Th } from "@/components/ui/table";
import type { DatasetPreview } from "@/lib/api/dataset-types";
import { dataModeLabel, dateRangeLabel, humanizeCode } from "@/lib/datasets/display";

/** Render a raw source row as labelled cells rather than a JSON blob. */
function RawValues({ raw }: { raw: Record<string, string> }) {
  const entries = Object.entries(raw);
  if (entries.length === 0) return <span className="text-slate-500">—</span>;
  return (
    <ul className="space-y-0.5">
      {entries.map(([header, value]) => (
        <li key={header} className="break-words">
          <span className="text-slate-500 dark:text-slate-400">{header}: </span>
          <span className="font-medium">{value === "" ? "—" : value}</span>
        </li>
      ))}
    </ul>
  );
}

export interface CleaningReviewStepProps {
  preview: DatasetPreview;
  onContinue: () => void;
  onBack: () => void;
}

export function CleaningReviewStep({
  preview,
  onContinue,
  onBack,
}: CleaningReviewStepProps) {
  const summary = preview.cleaning_summary;
  // Every count is shown, including zeros — a hidden zero reads as "unknown".
  const summaryRows: [string, string][] = [
    ["Total rows parsed", String(summary.total_rows_parsed)],
    ["Valid rows", String(summary.valid_rows)],
    ["Bad rows", String(summary.bad_rows)],
    ["Duplicate dates", String(summary.duplicate_dates)],
    ["Final row count", String(summary.final_row_count)],
    [
      "Date range",
      dateRangeLabel(summary.date_range?.start, summary.date_range?.end),
    ],
    ["Data mode", dataModeLabel(summary.data_mode)],
  ];

  return (
    <section aria-labelledby="cleaning-heading" className="space-y-6">
      <div>
        <h2 id="cleaning-heading" className="text-lg font-semibold">
          Review data cleaning
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          These are the server&apos;s results for the mapping you confirmed.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold">Summary</h3>
        <dl className="mt-2 grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
          {summaryRows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
              <dd className="font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div>
        <h3 className="text-sm font-semibold">Rejected-row reasons</h3>
        {Object.keys(summary.bad_row_reasons).length === 0 ? (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            No reason counts were reported.
          </p>
        ) : (
          <TableScroll label="Rejected-row reason counts">
            <Table caption="Count of rejected rows by reason">
              <thead>
                <tr>
                  <Th>Reason</Th>
                  <Th numeric>Rows</Th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.bad_row_reasons).map(([reason, count]) => (
                  <tr key={reason}>
                    <Td wrap>{humanizeCode(reason)}</Td>
                    <Td numeric>{count}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">
          Rejected rows ({preview.bad_rows.length})
        </h3>
        {preview.bad_rows.length === 0 ? (
          <div className="mt-2">
            <EmptyState title="No rejected rows">
              Every parsed row passed validation.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-2">
            <TableScroll label="Rejected rows">
              <Table caption="Rows rejected during cleaning, with their reason and original values">
                <thead>
                  <tr>
                    <Th numeric>Row</Th>
                    <Th>Reason</Th>
                    <Th>Original values</Th>
                  </tr>
                </thead>
                <tbody>
                  {preview.bad_rows.map((badRow) => (
                    <tr key={`${badRow.row_number}-${badRow.reason}`}>
                      <Td numeric>{badRow.row_number}</Td>
                      <Td wrap>{humanizeCode(badRow.reason)}</Td>
                      <Td wrap>
                        <RawValues raw={badRow.raw} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableScroll>
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">
          Duplicate dates ({preview.duplicate_rows.length})
        </h3>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          When two rows share a date, the one appearing last in the file is
          kept and the earlier one is discarded.
        </p>
        {preview.duplicate_rows.length === 0 ? (
          <div className="mt-2">
            <EmptyState title="No duplicate dates">
              Every row has a distinct date.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-2">
            <TableScroll label="Duplicate dates">
              <Table caption="Duplicate dates, showing which row was kept and which was discarded">
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Reason</Th>
                    <Th>Kept row</Th>
                    <Th>Discarded row</Th>
                  </tr>
                </thead>
                <tbody>
                  {preview.duplicate_rows.map((duplicate) => (
                    <tr
                      key={`${duplicate.date}-${duplicate.kept_row_number}-${duplicate.discarded_row_number}`}
                    >
                      <Td>{duplicate.date}</Td>
                      <Td wrap>{humanizeCode(duplicate.reason)}</Td>
                      <Td wrap>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          Row {duplicate.kept_row_number}
                        </p>
                        <RawValues raw={duplicate.kept_raw} />
                      </Td>
                      <Td wrap>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          Row {duplicate.discarded_row_number}
                        </p>
                        <RawValues raw={duplicate.discarded_raw} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableScroll>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onContinue}>I understand, continue</Button>
        <Button variant="ghost" onClick={onBack}>
          Back to column mapping
        </Button>
      </div>
    </section>
  );
}
