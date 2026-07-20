"use client";

import Link from "next/link";
import { useId, useRef } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { ACCEPTED_EXTENSIONS, fileSizeLabel } from "@/lib/datasets/display";

export interface UploadStepProps {
  file: File | null;
  fileError: string | null;
  requestError: string | null;
  pending: boolean;
  onSelectFile: (file: File | null) => void;
  onSubmit: () => void;
}

export function UploadStep({
  file,
  fileError,
  requestError,
  pending,
  onSelectFile,
  onSubmit,
}: UploadStepProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <section aria-labelledby="upload-heading" className="space-y-5">
      <h2 id="upload-heading" className="text-lg font-semibold">
        Upload price data
      </h2>

      {requestError && <Alert tone="error">{requestError}</Alert>}

      <FormField
        id={inputId}
        label="Price data file"
        description={`Accepted formats: ${ACCEPTED_EXTENSIONS.join(", ")}. A .xls file must be a TongdaXin text export (tab-separated text), not a regular binary Excel workbook.`}
        error={fileError ?? undefined}
      >
        {(aria) => (
          <input
            {...aria}
            ref={inputRef}
            type="file"
            name="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            aria-invalid={fileError ? true : undefined}
            onChange={(event) => onSelectFile(event.target.files?.[0] ?? null)}
            className="block w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 dark:border-slate-600 dark:file:bg-slate-800 dark:hover:file:bg-slate-700"
          />
        )}
      </FormField>

      {file && (
        <div className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-700">
          <p className="font-medium break-words">{file.name}</p>
          <p className="text-slate-600 dark:text-slate-400">{fileSizeLabel(file.size)}</p>
          <Button
            variant="ghost"
            className="mt-2 px-2"
            onClick={() => {
              // Clearing the input lets the same file be re-picked later.
              if (inputRef.current) inputRef.current.value = "";
              onSelectFile(null);
            }}
          >
            Replace file
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={onSubmit}
          pending={pending}
          pendingLabel="Reading file…"
          disabled={file === null}
        >
          Preview data
        </Button>
        <Link
          href="/datasets"
          className="text-sm font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400"
        >
          Or reuse a saved dataset
        </Link>
      </div>

      <p className="text-xs text-slate-500 dark:text-slate-400">
        The file is read in your browser and sent once for parsing. It is never
        stored in the browser and the server does not keep the raw upload.
      </p>
    </section>
  );
}
