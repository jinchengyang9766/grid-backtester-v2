"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DatasetSummary } from "@/lib/api/dataset-types";
import {
  dataModeLabel,
  dateRangeLabel,
  displayText,
  sourceTypeLabel,
  timestampLabel,
} from "@/lib/datasets/display";

export interface DatasetCardProps {
  dataset: DatasetSummary;
  busy: boolean;
  onViewDetails: (dataset: DatasetSummary) => void;
  onDelete: (dataset: DatasetSummary) => void;
}

export function DatasetCard({
  dataset,
  busy,
  onViewDetails,
  onDelete,
}: DatasetCardProps) {
  const facts: [string, string][] = [
    ["Security", displayText(dataset.security_name)],
    ["Code", displayText(dataset.security_code)],
    ["Source", sourceTypeLabel(dataset.source_type)],
    ["Original file", dataset.original_filename],
    ["Date range", dateRangeLabel(dataset.start_date, dataset.end_date)],
    ["Rows", String(dataset.row_count)],
    ["Created", timestampLabel(dataset.created_at)],
  ];

  return (
    <li className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-base font-semibold break-words">{dataset.name}</h3>
        <Badge tone="info">{dataModeLabel(dataset.data_mode)}</Badge>
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
        {facts.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4 flex flex-wrap gap-2">
        {/* Accessible names include the dataset, so they stay unique in a list. */}
        <Button
          variant="secondary"
          onClick={() => onViewDetails(dataset)}
          disabled={busy}
          aria-label={`View details for ${dataset.name}`}
        >
          View details
        </Button>
        <Link
          href={`/backtest/new?dataset_id=${dataset.id}`}
          aria-label={`Use ${dataset.name} for a backtest`}
          className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
        >
          Use for backtest
        </Link>
        <Button
          variant="destructive"
          onClick={() => onDelete(dataset)}
          disabled={busy}
          aria-label={`Delete ${dataset.name}`}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}
