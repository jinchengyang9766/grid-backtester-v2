"use client";

import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { BACKTEST_STATUSES, type BacktestStatus } from "@/lib/api/backtest-types";
import type { DatasetSummary } from "@/lib/api/dataset-types";
import { statusLabel } from "@/lib/backtests/display";

export interface HistoryFilterValues {
  search: string;
  datasetId: number | null;
  status: BacktestStatus | null;
}

export interface HistoryFiltersProps {
  values: HistoryFilterValues;
  datasets: readonly DatasetSummary[];
  disabled?: boolean;
  onChange: (values: HistoryFilterValues) => void;
}

const SELECT_CLASS =
  "block w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 disabled:bg-slate-100 dark:border-slate-600 dark:bg-slate-900 dark:disabled:bg-slate-800";

export function HistoryFilters({
  values,
  datasets,
  disabled,
  onChange,
}: HistoryFiltersProps) {
  const searchId = useId();
  const datasetId = useId();
  const statusId = useId();

  // Typing is debounced locally so each keystroke is not a request; the
  // request itself is never retried, and superseded ones are aborted.
  const [searchDraft, setSearchDraft] = useState(values.search);

  // Adjusting state during render (React's documented pattern) rather than in
  // an effect: this only fires when the applied search changes externally,
  // e.g. browser back/forward restoring a different query string.
  const [appliedSearch, setAppliedSearch] = useState(values.search);
  if (values.search !== appliedSearch) {
    setAppliedSearch(values.search);
    setSearchDraft(values.search);
  }

  useEffect(() => {
    if (searchDraft === values.search) return;
    const timer = setTimeout(() => {
      onChange({ ...values, search: searchDraft });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchDraft, values, onChange]);

  const hasFilters =
    values.search !== "" || values.datasetId !== null || values.status !== null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:items-end">
      <FormField id={searchId} label="Search by name">
        {(aria) => (
          <Input
            {...aria}
            type="search"
            value={searchDraft}
            disabled={disabled}
            placeholder="Backtest name"
            onChange={(event) => setSearchDraft(event.target.value)}
          />
        )}
      </FormField>

      <FormField id={datasetId} label="Dataset">
        {(aria) => (
          <select
            {...aria}
            className={SELECT_CLASS}
            disabled={disabled}
            value={values.datasetId === null ? "" : String(values.datasetId)}
            onChange={(event) =>
              onChange({
                ...values,
                datasetId: event.target.value === "" ? null : Number(event.target.value),
              })
            }
          >
            <option value="">All datasets</option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        )}
      </FormField>

      <FormField id={statusId} label="Status">
        {(aria) => (
          <select
            {...aria}
            className={SELECT_CLASS}
            disabled={disabled}
            value={values.status ?? ""}
            onChange={(event) =>
              onChange({
                ...values,
                status:
                  event.target.value === ""
                    ? null
                    : (event.target.value as BacktestStatus),
              })
            }
          >
            <option value="">All statuses</option>
            {BACKTEST_STATUSES.map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
        )}
      </FormField>

      <div>
        <Button
          variant="secondary"
          disabled={disabled || !hasFilters}
          onClick={() => onChange({ search: "", datasetId: null, status: null })}
        >
          Clear filters
        </Button>
      </div>
    </div>
  );
}
