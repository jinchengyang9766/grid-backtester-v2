"use client";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import type { DatasetSummary } from "@/lib/api/dataset-types";

export interface DeleteDatasetDialogProps {
  dataset: DatasetSummary | null;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteDatasetDialog({
  dataset,
  pending,
  error,
  onCancel,
  onConfirm,
}: DeleteDatasetDialogProps) {
  if (dataset === null) return null;

  return (
    <Dialog
      open
      title="Delete dataset"
      description={`This permanently deletes "${dataset.name}".`}
      onClose={pending ? () => undefined : onCancel}
      // A stray backdrop click must not dismiss a destructive confirmation.
      dismissOnBackdrop={false}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            pending={pending}
            pendingLabel="Deleting…"
          >
            Delete dataset
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        {error && <Alert tone="error">{error}</Alert>}
        <p>
          <span className="font-medium break-words">{dataset.name}</span> and its{" "}
          {dataset.row_count} saved price rows will be removed.
        </p>
        <ul className="list-inside list-disc space-y-1 text-slate-700 dark:text-slate-300">
          <li>This cannot be undone.</li>
          <li>
            Deletion is refused while any saved backtest still uses this
            dataset. Delete those backtests first.
          </li>
        </ul>
      </div>
    </Dialog>
  );
}
