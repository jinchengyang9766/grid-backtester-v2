"use client";

/**
 * `/history/{id}` — one owned run's full persisted result.
 *
 * The detail is requested once with every series include; ownership is
 * enforced by the backend's indistinguishable 404. Nothing is re-executed and
 * no metric is recomputed.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  DeleteBacktestDialog,
  RenameBacktestDialog,
  RerunBacktestDialog,
} from "@/components/backtests/backtest-action-dialogs";
import { DuplicateBacktestDialog } from "@/components/backtests/duplicate-backtest-dialog";
import { BacktestDashboard } from "@/components/results/backtest-dashboard";
import { ExportControls } from "@/components/results/export-controls";
import { ResultStatus } from "@/components/results/result-status";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { isConfigurationErrorCode } from "@/lib/api/backtest-types";
import {
  BACKTEST_INCLUDES,
  type BacktestDetailWithSeries,
} from "@/lib/api/backtest-history-types";
import {
  deleteBacktest,
  duplicateBacktest,
  getBacktestDetail,
  renameBacktest,
  rerunBacktest,
} from "@/lib/api/backtest-history";
import { ApiClientError } from "@/lib/api/errors";
import {
  serializeConfiguration,
  type ConfigurationFormState,
} from "@/lib/backtests/configuration-state";
import { configurationToFormState } from "@/lib/backtests/configuration-overrides";
import {
  backendFieldError,
  isGridSectionCode,
  validateConfiguration,
  type FieldErrors,
} from "@/lib/backtests/configuration-validation";

const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(error: unknown): string {
  return error instanceof ApiClientError ? error.message : GENERIC_FAILURE;
}

export function BacktestDetailPage({ backtestId }: { backtestId: number }) {
  const router = useRouter();

  const [detail, setDetail] = useState<BacktestDetailWithSeries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [duplicateConfig, setDuplicateConfig] = useState<ConfigurationFormState | null>(null);
  const [duplicateErrors, setDuplicateErrors] = useState<FieldErrors>({});
  const [duplicateFormError, setDuplicateFormError] = useState<string | null>(null);
  const [duplicateGridError, setDuplicateGridError] = useState<string | null>(null);

  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const mounted = useRef(true);
  // Only the newest detail request may publish, so navigating between runs
  // cannot attach an older response to a newer route id.
  const detailGeneration = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++detailGeneration.current;
    let cancelled = false;

    void (async () => {
      try {
        const response = await getBacktestDetail(backtestId, {
          include: [...BACKTEST_INCLUDES],
          signal: controller.signal,
        });
        if (cancelled || !mounted.current || generation !== detailGeneration.current) return;
        setDetail(response);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (cancelled || !mounted.current || generation !== detailGeneration.current) return;
        setError(messageOf(caught));
      } finally {
        if (!cancelled && mounted.current && generation === detailGeneration.current) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [backtestId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setDetail(null);
    setReloadKey((key) => key + 1);
  }, []);

  async function submitRename(name: string) {
    if (actionPending || detail === null) return;
    setActionPending(true);
    setActionError(null);
    try {
      await renameBacktest(detail.id, name);
      if (!mounted.current) return;
      setDetail((current) => (current === null ? current : { ...current, name }));
      setRenameOpen(false);
    } catch (caught) {
      if (mounted.current) setActionError(messageOf(caught));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function confirmDelete() {
    if (actionPending || detail === null) return;
    setActionPending(true);
    setActionError(null);
    try {
      await deleteBacktest(detail.id);
      if (!mounted.current) return;
      router.push("/history");
    } catch (caught) {
      if (mounted.current) setActionError(messageOf(caught));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function confirmRerun() {
    if (actionPending || detail === null) return;
    setActionPending(true);
    setActionError(null);
    try {
      const created = await rerunBacktest(detail.id);
      if (!mounted.current) return;
      setRerunOpen(false);
      router.push(`/history/${created.id}`);
    } catch (caught) {
      if (mounted.current) setActionError(messageOf(caught));
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  async function submitDuplicate() {
    if (actionPending || detail === null || duplicateConfig === null) return;

    const validation = validateConfiguration(duplicateConfig);
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
        detail.id,
        serializeConfiguration(duplicateConfig, detail.dataset.data_mode),
      );
      if (!mounted.current) return;
      setDuplicateConfig(null);
      router.push(`/history/${created.id}`);
    } catch (caught) {
      if (!mounted.current) return;
      if (caught instanceof ApiClientError) {
        setDuplicateFormError(caught.message);
        if (isConfigurationErrorCode(caught.code)) {
          const hint = backendFieldError(caught.details);
          if (hint !== null) setDuplicateErrors({ [hint.path]: caught.message });
          if (isGridSectionCode(caught.code)) setDuplicateGridError(caught.message);
        }
      } else {
        setDuplicateFormError(GENERIC_FAILURE);
      }
    } finally {
      if (mounted.current) setActionPending(false);
    }
  }

  if (loading) return <LoadingState label="Loading backtest…" />;

  if (error !== null || detail === null) {
    return (
      <Alert
        tone="error"
        title="Backtest unavailable"
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={retry}>
              Try again
            </Button>
            <Link
              href="/history"
              className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Back to history
            </Link>
          </div>
        }
      >
        {error ?? "Backtest not found."}
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight break-words">
              {detail.name}
            </h1>
            <ResultStatus status={detail.status} />
          </div>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            <Link
              href="/history"
              className="text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400"
            >
              Back to history
            </Link>
          </p>
        </div>
      </div>

      {actionError && <Alert tone="error">{actionError}</Alert>}

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={actionPending} onClick={() => setRenameOpen(true)}>
          Rename
        </Button>
        <Button variant="secondary" disabled={actionPending} onClick={() => setRerunOpen(true)}>
          Rerun
        </Button>
        <Button
          variant="secondary"
          disabled={actionPending}
          onClick={() => {
            setDuplicateConfig(configurationToFormState(detail.configuration));
            setDuplicateErrors({});
            setDuplicateFormError(null);
            setDuplicateGridError(null);
          }}
        >
          Duplicate
        </Button>
        <Button variant="destructive" disabled={actionPending} onClick={() => setDeleteOpen(true)}>
          Delete
        </Button>
      </div>

      {/* Rendered only once an owned detail has loaded, so an ownership 404
          never offers a download. */}
      <ExportControls backtestId={detail.id} status={detail.status} />

      <BacktestDashboard detail={detail} />

      <RenameBacktestDialog
        open={renameOpen}
        currentName={detail.name}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setRenameOpen(false);
          setActionError(null);
        }}
        onSubmit={(name) => void submitRename(name)}
      />

      <DeleteBacktestDialog
        open={deleteOpen}
        runName={detail.name}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setDeleteOpen(false);
          setActionError(null);
        }}
        onConfirm={() => void confirmDelete()}
      />

      <RerunBacktestDialog
        open={rerunOpen}
        runName={detail.name}
        datasetName={detail.dataset.name}
        pending={actionPending}
        error={actionError}
        onCancel={() => {
          setRerunOpen(false);
          setActionError(null);
        }}
        onConfirm={() => void confirmRerun()}
      />

      {duplicateConfig !== null && (
        <DuplicateBacktestDialog
          open
          sourceName={detail.name}
          dataset={detail.dataset}
          configuration={duplicateConfig}
          errors={duplicateErrors}
          formError={duplicateFormError}
          gridError={duplicateGridError}
          pending={actionPending}
          onChange={setDuplicateConfig}
          onReset={() => setDuplicateConfig(configurationToFormState(detail.configuration))}
          onCancel={() => setDuplicateConfig(null)}
          onSubmit={() => void submitDuplicate()}
        />
      )}
    </div>
  );
}
