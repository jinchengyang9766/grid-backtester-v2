import type { ReactNode } from "react";

export interface FormFieldProps {
  /** Must match the control's `id` so the label is programmatically bound. */
  id: string;
  label: string;
  description?: string;
  error?: string;
  children: (aria: {
    id: string;
    "aria-describedby": string | undefined;
  }) => ReactNode;
}

/**
 * Wraps one labelled control, wiring its description and error text through
 * `aria-describedby` so both are announced when the field receives focus.
 */
export function FormField({
  id,
  label,
  description,
  error,
  children,
}: FormFieldProps) {
  const descriptionId = description ? `${id}-description` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block text-sm font-medium text-slate-800 dark:text-slate-200"
      >
        {label}
      </label>
      {description && (
        <p id={descriptionId} className="text-xs text-slate-600 dark:text-slate-400">
          {description}
        </p>
      )}
      {children({ id, "aria-describedby": describedBy })}
      {error && (
        <p
          id={errorId}
          // Field errors appear after interaction, so announce them politely.
          role="alert"
          className="text-sm text-red-700 dark:text-red-400"
        >
          {error}
        </p>
      )}
    </div>
  );
}
