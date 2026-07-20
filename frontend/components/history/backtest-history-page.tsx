"use client";

/**
 * `/history` — the authenticated workspace (SPEC Section 27).
 *
 * Filters live in the URL so back/forward restores them, but only
 * identifiers and filter values ever go there — never result data. Every
 * request is abortable and generation-guarded, so a slow response for an
 * older filter can never replace a newer one.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  DeleteBacktestDialog,
  RenameBacktestDialog,
  RerunBacktestDialog,
} from "@/components/backtests/backtest-action-dialogs";
import { DuplicateBacktestDialog } from "@/components/backtests/duplicate-backtest-dialog";
import { HistoryCard } from "@/components/history/history-card";
import { HistoryFilters, type HistoryFilterValues } from "@/components/history/history-filters";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingState } from "@/components/ui/loading-state";
import type { BacktestStatus } from "@/lib/api/backtest-types";
import type {
  BacktestListItem,
  BacktestListResponse,
} from "@/lib/api/backtest-history-types";
import {
  deleteBacktest,
  duplicateBacktest,
  getBacktestDetail,
  listBacktests,
  renameBacktest,
  rerunBacktest,
} from "@/lib/api/backtest-history";
import type { DatasetSummary } from "@/lib/api/dataset-types";
import { listDatasets } from "@/lib/api/datasets";
import { ApiClientError } from "@/lib/api/errors";
import {
  serializeConfiguration,
  type ConfigurationFormState,
  type StrategyDatasetSummary,
} from "@/lib/backtests/configuration-state";
import { configurationToFormState } from "@/lib/backtests/configuration-overrides";
import {
  backendFieldError,
  isGridSectionCode,
  validateConfiguration,
  type FieldErrors,
} from "@/lib/backtests/configuration-validation";
import { isConfigurationErrorCode } from "@/lib/api/backtest-types";

const PAGE_SIZE = 20;
const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(error: unknown): string {
  return error instanceof ApiClientError ? error.message : GENERIC_FAILURE;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

type ListState =
  | { status: "loading" }
  | { status: "loaded"; page: BacktestListResponse }
  | { status: "error"; message: string };

interface DuplicateState {
  run: BacktestListItem;
  dataset: StrategyDatasetSummary;
  configuration: ConfigurationFormState;
}

export function BacktestHistoryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const filters = useMemo<HistoryFilterValues>(() => {
    const status = searchParams.get("status");
    const datasetId = searchParams.get("dataset_id");
    return {
      search: searchParams.get("search") ?? "",
      datasetId: datasetId !== null && /^\d+$/.test(datasetId) ? Number(datasetId) : null,
      status: status === null ? null : (status as BacktestStatus),
    };
  }, [searchParams]);

  const pageParam = searchParams.get("page");
  const page = pageParam !== null && /^\d+$/.test(pageParam) ? Math.max(1, Number(pageParam)) : 1;
  const offset = (page - 1) * PAGE_SIZE;

  const [list, setList] = useState<ListState>({ status: "loading" });
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const [selected, setSelected] = useState<number[]>([]);

  const [renameTarget, setRenameTarget] = useState<BacktestListItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BacktestListItem | null>(null);
  const [rerunTarget, setRerunTarget] = useState<BacktestListItem | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateState | null>(null);
  const [duplicateErrors, setDuplicateErrors] = useState<FieldErrors>({});
  const [duplicateFormError, setDuplicateFormError] = useState<string | null>(null);
  const [duplicateGridError, setDuplicateGridError] = useState<string | null>(null);

  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const mounted = useRef(true);
  const listGeneration = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Dataset options for the filter; one request, not one per row.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        const response = await listDatasets(controller.signal);
        if (!cancelled && mounted.current) setDatasets(response.items);
      } catch {
        // A filter that cannot be populated is not worth blocking history for.
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++listGeneration.current;
    let cancelled = false;

    void (async () => {
      try {
        const response = await listBacktests(
          {
            search: filters.search,
            dataset_id: filters.datasetId ?? undefined,
            status: filters.status ?? undefined,
            limit: PAGE_SIZE,
            offset,
          },
          controller.signal,
        );
        if (cancelled || !mounted.current || generation !== listGeneration.current) return;
        setList({ status: "loaded", page: response });
      } catch (error) {
        if (isAbort(error) || cancelled || !mounted.current) return;
        if (generation !== listGeneration.current) return;
        setList({ status: "error", message: messageOf(error) });
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [filters.search, filters.datasetId, filters.status, offset, reloadKey]);

  const pushParams = useCallback(
    (next: HistoryFilterValues, nextPage: number) => {
      const params = new URLSearchParams();
      if (next.search.trim() !== "") params.set("search", next.search.trim());
      if (next.datasetId !== null) params.set("dataset_id", String(next.datasetId));
      if (next.status !== null) params.set("status", next.status);
      if (nextPage > 1) params.set("page", String(nextPage));
      const query = params.toString();
      router.push(query === "" ? "/history" : `/history?${query}`);
    },
    [router],
  );

  const handleFilterChange = useCallback(
    (next: HistoryFilterValues) => {
      // A filter change resets paging and clears any comparison selection,
      // so the compared set always matches what is on screen.
      if (selected.length > 0) {
        setSelected([]);
        setAnnouncement("Comparison selection cleared because the filters changed.");
      }
      setList({ status: "loading" });
      pushParams(next, 1);
    },
    [pushParams, selected.length],
  );

  const goToPage = useCallback(
    (nextPage: number) => {
      if (selected.length > 0) {
        setSelected([]);
        setAnnouncement("Comparison selection cleared because the page changed.");
      }
      setList({ status: "loading" });
      pushParams(filters, nextPage);
    },
    [filters, pushParams, selected.length],
  );

  const reload = useCallback(() => {
    setList({ status: "loading" });
    setReloadKey((key) => key + 1);
  }, []);

  const items = list.status === "loaded" ? list.page.items : [];
  const total = list.status === "loaded" ? list.page.total : 0;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function toggleSelected(run: BacktestListItem) {
    setSelected((current) =>
      current.includes(run.id)
        ? current.filter((id) => id !== run.id)
        : [...current, run.id],
    );
  }

  async function submitRename(name: string) {
    if (actionPending || renameTarget === null) return;
    setActionPending(true);
    setActionError(null);
    try {
      await renameBacktest(renameTarget.id, name);
      if (!mounted.current) return;
      setList((current) =>
        current.status === "loaded"
          ? {
              status: "loaded",
              page: {
                ...current.page,
                items: current.page.items.map((item) =>
                  item.id === renameTarget.id ? { ...item, name } : item,
                ),
              },
            }
          : current,
      );
      setRenameTarget(null);
      setAnnouncement(`Backtest renamed to ${name}.`);
    } catch (error) {
      if (mounted.current) setActionError(messageOf(error));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function confirmDelete() {
    if (actionPending || deleteTarget === null) return;
    const target = deleteTarget;
    setActionPending(true);
    setActionError(null);
    try {
      await deleteBacktest(target.id);
      if (!mounted.current) return;
      // Removed only after the server confirms 204.
      setList((current) =>
        current.status === "loaded"
          ? {
              status: "loaded",
              page: {
                ...current.page,
                items: current.page.items.filter((item) => item.id !== target.id),
                total: Math.max(0, current.page.total - 1),
              },
            }
          : current,
      );
      setSelected((current) => current.filter((id) => id !== target.id));
      setDeleteTarget(null);
      setAnnouncement(`Backtest ${target.name} deleted.`);
    } catch (error) {
      if (mounted.current) setActionError(messageOf(error));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function confirmRerun() {
    if (actionPending || rerunTarget === null) return;
    setActionPending(true);
    setActionError(null);
    try {
      const created = await rerunBacktest(rerunTarget.id);
      if (!mounted.current) return;
      setRerunTarget(null);
      // COMPLETED and FAILED alike are created runs worth opening.
      router.push(`/history/${created.id}`);
    } catch (error) {
      if (mounted.current) setActionError(messageOf(error));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function openDuplicate(run: BacktestListItem) {
    if (actionPending) return;
    setActionPending(true);
    setActionError(null);
    try {
      // The source configuration lives on the detail response, not the list.
      const detail = await getBacktestDetail(run.id);
      if (!mounted.current) return;
      setDuplicate({
        run,
        dataset: detail.dataset,
        configuration: configurationToFormState(detail.configuration),
      });
      setDuplicateErrors({});
      setDuplicateFormError(null);
      setDuplicateGridError(null);
    } catch (error) {
      if (mounted.current) setActionError(messageOf(error));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function submitDuplicate() {
    if (actionPending || duplicate === null) return;

    const validation = validateConfiguration(duplicate.configuration);
    if (!validation.valid) {
      setDuplicateErrors(validation.fieldErrors);
      setDuplicateFormError("Fix the highlighted fields before running.");
      return;
    }
    setDuplicateErrors({});
    setDuplicateFormError(null);
    setDuplicateGridError(null);
    setActionPending(true);

    try {
      const created = await duplicateBacktest(
        duplicate.run.id,
        serializeConfiguration(duplicate.configuration, duplicate.dataset.data_mode),
      );
      if (!mounted.current) return;
      setDuplicate(null);
      router.push(`/history/${created.id}`);
    } catch (error) {
      if (!mounted.current) return;
      // Edited values are preserved for correction.
      if (error instanceof ApiClientError) {
        setDuplicateFormError(error.message);
        if (isConfigurationErrorCode(error.code)) {
          const hint = backendFieldError(error.details);
          if (hint !== null) setDuplicateErrors({ [hint.path]: error.message });
          if (isGridSectionCode(error.code)) setDuplicateGridError(error.message);
        }
      } else {
        setDuplicateFormError(GENERIC_FAILURE);
      }
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  return (
    <div className="space-y-6">
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {actionError && <Alert tone="error">{actionError}</Alert>}

      <HistoryFilters
        values={filters}
        datasets={datasets}
        disabled={actionPending}
        onChange={handleFilterChange}
      />

      {list.status === "loading" && <LoadingState label="Loading backtests…" />}

      {list.status === "error" && (
        <Alert
          tone="error"
          title="Could not load your backtests"
          action={
            <Button variant="secondary" onClick={reload}>
              Try again
            </Button>
          }
        >
          {list.message}
        </Alert>
      )}

      {list.status === "loaded" && (
        <>
          <p aria-live="polite" className="text-sm text-slate-600 dark:text-slate-400">
            {total} backtest{total === 1 ? "" : "s"} found
            {total > 0 && ` · showing ${items.length} on page ${page} of ${maxPage}`}
          </p>

          {items.length === 0 ? (
            filters.search !== "" || filters.datasetId !== null || filters.status !== null ? (
              <EmptyState
                title="No backtests match these filters"
                action={
                  <Button
                    variant="secondary"
                    onClick={() =>
                      handleFilterChange({ search: "", datasetId: null, status: null })
                    }
                  >
                    Clear filters
                  </Button>
                }
              >
                Try a different name, dataset, or status.
              </EmptyState>
            ) : (
              <EmptyState
                title="No backtests yet"
                action={
                  <Link
                    href="/backtest/new"
                    className="inline-flex items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                  >
                    Run your first backtest
                  </Link>
                }
              >
                Import price data and configure a strategy to get started.
              </EmptyState>
            )
          ) : (
            <ul className="space-y-3">
              {items.map((run) => (
                <HistoryCard
                  key={run.id}
                  run={run}
                  selected={selected.includes(run.id)}
                  busy={actionPending}
                  onToggleSelected={toggleSelected}
                  onRename={setRenameTarget}
                  onRerun={setRerunTarget}
                  onDuplicate={(item) => void openDuplicate(item)}
                  onDelete={setDeleteTarget}
                />
              ))}
            </ul>
          )}

          {total > PAGE_SIZE && (
            <nav aria-label="History pagination" className="flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                disabled={page <= 1 || actionPending}
                onClick={() => goToPage(page - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-slate-600 dark:text-slate-400">
                Page {page} of {maxPage}
              </span>
              <Button
                variant="secondary"
                disabled={page >= maxPage || actionPending}
                onClick={() => goToPage(page + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}

      {selected.length > 0 && (
        <div className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-md border border-slate-300 bg-white p-3 shadow-sm dark:border-slate-600 dark:bg-slate-900">
          <p className="text-sm">
            {selected.length} selected for comparison
            {selected.length === 1 && " — select at least one more"}
          </p>
          <Link
            href={`/history/compare?ids=${selected.join(",")}`}
            aria-disabled={selected.length < 2}
            className={`inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 ${
              selected.length < 2
                ? "pointer-events-none bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500"
                : "bg-sky-700 text-white hover:bg-sky-800"
            }`}
            tabIndex={selected.length < 2 ? -1 : undefined}
          >
            Compare selected
          </Link>
          <Button variant="ghost" onClick={() => setSelected([])}>
            Clear selection
          </Button>
        </div>
      )}

      <RenameBacktestDialog
        open={renameTarget !== null}
        currentName={renameTarget?.name ?? ""}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setRenameTarget(null);
          setActionError(null);
        }}
        onSubmit={(name) => void submitRename(name)}
      />

      <DeleteBacktestDialog
        open={deleteTarget !== null}
        runName={deleteTarget?.name ?? ""}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setDeleteTarget(null);
          setActionError(null);
        }}
        onConfirm={() => void confirmDelete()}
      />

      <RerunBacktestDialog
        open={rerunTarget !== null}
        runName={rerunTarget?.name ?? ""}
        datasetName={rerunTarget?.dataset_name ?? ""}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setRerunTarget(null);
          setActionError(null);
        }}
        onConfirm={() => void confirmRerun()}
      />

      {duplicate !== null && (
        <DuplicateBacktestDialog
          open
          sourceName={duplicate.run.name}
          dataset={duplicate.dataset}
          configuration={duplicate.configuration}
          errors={duplicateErrors}
          formError={duplicateFormError}
          gridError={duplicateGridError}
          pending={actionPending}
          onChange={(configuration) =>
            setDuplicate((current) => (current === null ? current : { ...current, configuration }))
          }
          onReset={() =>
            setDuplicate((current) =>
              current === null
                ? current
                : { ...current, configuration: configurationToFormState({}) },
            )
          }
          onCancel={() => setDuplicate(null)}
          onSubmit={() => void submitDuplicate()}
        />
      )}
    </div>
  );
}
