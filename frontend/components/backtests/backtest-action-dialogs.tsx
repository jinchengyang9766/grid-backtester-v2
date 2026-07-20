"use client";

/**
 * Rename, delete, and rerun confirmations.
 *
 * Each is a single-purpose dialog that owns its own pending state, so a
 * repeated click cannot issue a second write. None of them retries.
 */

import { useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";

export interface RenameDialogProps {
  open: boolean;
  currentName: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (name: string) => void;
}

/**
 * Mounted only while the dialog is open, so `useState` prefills the current
 * name on every open without an effect syncing state to a prop.
 */
export function RenameBacktestDialog(props: RenameDialogProps) {
  if (!props.open) return null;
  return <RenameDialogBody key={props.currentName} {...props} />;
}

function RenameDialogBody({
  currentName,
  pending,
  error,
  onCancel,
  onSubmit,
}: RenameDialogProps) {
  const nameId = useId();
  const [name, setName] = useState(currentName);
  const [localError, setLocalError] = useState<string | null>(null);

  function submit() {
    if (pending) return;
    const trimmed = name.trim();
    if (trimmed === "") {
      setLocalError("Enter a name for this backtest.");
      return;
    }
    setLocalError(null);
    onSubmit(trimmed);
  }

  return (
    <Dialog
      open
      title="Rename backtest"
      description="Only the name changes; the configuration and results are untouched."
      onClose={pending ? () => undefined : onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={submit} pending={pending} pendingLabel="Saving…">
            Save name
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        <FormField id={nameId} label="Name" error={localError ?? undefined}>
          {(aria) => (
            <Input
              {...aria}
              data-autofocus
              value={name}
              invalid={Boolean(localError)}
              disabled={pending}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submit();
                }
              }}
            />
          )}
        </FormField>
      </div>
    </Dialog>
  );
}

export interface DeleteDialogProps {
  open: boolean;
  runName: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteBacktestDialog({
  open,
  runName,
  pending,
  error,
  onCancel,
  onConfirm,
}: DeleteDialogProps) {
  if (!open) return null;
  return (
    <Dialog
      open
      title="Delete backtest"
      description={`This permanently deletes "${runName}".`}
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
            Delete backtest
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        {error && <Alert tone="error">{error}</Alert>}
        <p>
          <span className="font-medium break-words">{runName}</span> and all of its
          stored results — trades, zone events, and equity rows — will be removed.
        </p>
        <ul className="list-inside list-disc space-y-1 text-slate-700 dark:text-slate-300">
          <li>This cannot be undone.</li>
          <li>The dataset and its price data are not affected.</li>
        </ul>
      </div>
    </Dialog>
  );
}

export interface RerunDialogProps {
  open: boolean;
  runName: string;
  datasetName: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function RerunBacktestDialog({
  open,
  runName,
  datasetName,
  pending,
  error,
  onCancel,
  onConfirm,
}: RerunDialogProps) {
  if (!open) return null;
  return (
    <Dialog
      open
      title="Rerun backtest"
      description="Creates a new run from this one's saved configuration."
      onClose={pending ? () => undefined : onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={onConfirm} pending={pending} pendingLabel="Running…">
            Rerun
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        {error && <Alert tone="error">{error}</Alert>}
        <p>
          <span className="font-medium break-words">{runName}</span> will be
          re-executed using its stored configuration against the current price
          data in <span className="font-medium break-words">{datasetName}</span>.
        </p>
        <ul className="list-inside list-disc space-y-1 text-slate-700 dark:text-slate-300">
          <li>A new backtest is created; this one is left unchanged.</li>
          <li>
            If the dataset has changed since the original run, the result may
            differ.
          </li>
          <li>The run happens in one request, so this may take a moment.</li>
        </ul>
      </div>
    </Dialog>
  );
}
