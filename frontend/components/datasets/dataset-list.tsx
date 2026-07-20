"use client";

/**
 * Dataset management (SPEC Section 27's `/datasets`).
 *
 * There is no Dataset update endpoint, so no rename/edit control exists here.
 * Deletion is never optimistic: a row leaves the list only after the server
 * confirms 204, because a 409 DATASET_IN_USE is a normal outcome.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { DatasetCard } from "@/components/datasets/dataset-card";
import { DatasetDetailPanel } from "@/components/datasets/dataset-detail-panel";
import { DeleteDatasetDialog } from "@/components/datasets/delete-dataset-dialog";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingState } from "@/components/ui/loading-state";
import {
  DATASET_IN_USE,
  DATASET_NOT_FOUND,
  type DatasetDetail,
  type DatasetSummary,
} from "@/lib/api/dataset-types";
import { ApiClientError } from "@/lib/api/errors";
import { deleteDataset, getDataset, listDatasets } from "@/lib/api/datasets";

const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(error: unknown): string {
  return error instanceof ApiClientError ? error.message : GENERIC_FAILURE;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

type ListState =
  | { status: "loading" }
  | { status: "loaded"; items: DatasetSummary[] }
  | { status: "error"; message: string };

export function DatasetList() {
  const [list, setList] = useState<ListState>({ status: "loading" });

  const [selected, setSelected] = useState<DatasetSummary | null>(null);
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [pendingDelete, setPendingDelete] = useState<DatasetSummary | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");

  const mounted = useRef(true);
  const listController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);
  // Only the newest detail request may publish, so a slow response for a
  // previously-clicked dataset cannot replace a newer selection.
  const detailGeneration = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      listController.current?.abort();
      detailController.current?.abort();
    };
  }, []);

  // Bumping this key re-runs the load effect. The fetch lives in the effect
  // so no state is set synchronously in its body, only after the await.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listController.current = controller;
    let cancelled = false;

    void (async () => {
      try {
        const response = await listDatasets(controller.signal);
        if (cancelled || !mounted.current) return;
        setList({ status: "loaded", items: response.items });
      } catch (error) {
        if (isAbort(error) || cancelled || !mounted.current) return;
        setList({ status: "error", message: messageOf(error) });
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reloadKey]);

  const retryList = useCallback(() => {
    setList({ status: "loading" });
    setReloadKey((key) => key + 1);
  }, []);

  const openDetail = useCallback(async (dataset: DatasetSummary) => {
    detailController.current?.abort();
    const controller = new AbortController();
    detailController.current = controller;
    const generation = ++detailGeneration.current;

    setSelected(dataset);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);

    try {
      const response = await getDataset(dataset.id, controller.signal);
      if (!mounted.current || generation !== detailGeneration.current) return;
      setDetail(response);
    } catch (error) {
      if (isAbort(error)) return;
      if (!mounted.current || generation !== detailGeneration.current) return;
      setDetailError(messageOf(error));
    } finally {
      if (mounted.current && generation === detailGeneration.current) {
        setDetailLoading(false);
      }
    }
  }, []);

  const closeDetail = useCallback(() => {
    detailController.current?.abort();
    detailGeneration.current += 1;
    setSelected(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (deletePending || pendingDelete === null) return;
    const target = pendingDelete;
    setDeletePending(true);
    setDeleteError(null);

    try {
      await deleteDataset(target.id);
      if (!mounted.current) return;
      setList((current) =>
        current.status === "loaded"
          ? {
              status: "loaded",
              items: current.items.filter((item) => item.id !== target.id),
            }
          : current,
      );
      if (selected?.id === target.id) closeDetail();
      setPendingDelete(null);
      setAnnouncement(`Dataset ${target.name} deleted.`);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiClientError && error.code === DATASET_IN_USE) {
        // The dataset stays; dependent backtests must go first.
        setDeleteError(
          `${error.message} Delete the backtests that use this dataset first.`,
        );
      } else if (error instanceof ApiClientError && error.code === DATASET_NOT_FOUND) {
        // Already gone: drop the stale row without implying anything about
        // whether someone else's dataset exists.
        setList((current) =>
          current.status === "loaded"
            ? {
                status: "loaded",
                items: current.items.filter((item) => item.id !== target.id),
              }
            : current,
        );
        if (selected?.id === target.id) closeDetail();
        setPendingDelete(null);
        setAnnouncement("That dataset is no longer available.");
      } else {
        setDeleteError(messageOf(error));
      }
    } finally {
      if (mounted.current) setDeletePending(false);
    }
  }, [closeDetail, deletePending, pendingDelete, selected]);

  return (
    <div className="space-y-6">
      {/* Success and removal messages are announced, not only shown. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {list.status === "loading" && <LoadingState label="Loading datasets…" />}

      {list.status === "error" && (
        <Alert
          tone="error"
          title="Could not load your datasets"
          action={
            <Button variant="secondary" onClick={retryList}>
              Try again
            </Button>
          }
        >
          {list.message}
        </Alert>
      )}

      {list.status === "loaded" && list.items.length === 0 && (
        <EmptyState
          title="No datasets yet"
          action={
            <Link
              href="/backtest/new"
              className="inline-flex items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            >
              Upload price data
            </Link>
          }
        >
          Upload a TongdaXin text-export .xls or a .csv file to create your
          first dataset.
        </EmptyState>
      )}

      {list.status === "loaded" && list.items.length > 0 && (
        <ul className="space-y-3">
          {list.items.map((dataset) => (
            <DatasetCard
              key={dataset.id}
              dataset={dataset}
              busy={deletePending && pendingDelete?.id === dataset.id}
              onViewDetails={(item) => void openDetail(item)}
              onDelete={(item) => {
                setDeleteError(null);
                setPendingDelete(item);
              }}
            />
          ))}
        </ul>
      )}

      <DatasetDetailPanel
        open={selected !== null}
        loading={detailLoading}
        error={detailError}
        detail={detail}
        fallbackName={selected?.name ?? "Dataset"}
        onClose={closeDetail}
        onRetry={() => selected && void openDetail(selected)}
      />

      <DeleteDatasetDialog
        dataset={pendingDelete}
        pending={deletePending}
        error={deleteError}
        onCancel={() => {
          setPendingDelete(null);
          setDeleteError(null);
        }}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
