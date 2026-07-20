import type { ReactNode } from "react";

type Tone = "error" | "success" | "info";

export interface AlertProps {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  /** Rendered inside the alert, e.g. a retry control. */
  action?: ReactNode;
}

const TONES: Record<Tone, { container: string; label: string }> = {
  error: {
    container:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
    label: "Error",
  },
  success: {
    container:
      "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
    label: "Success",
  },
  info: {
    container:
      "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100",
    label: "Information",
  },
};

/**
 * A live region so a message that appears after submission is announced.
 * Errors use `role="alert"` (assertive); other tones use a polite status.
 */
export function Alert({ tone = "info", title, children, action }: AlertProps) {
  const styles = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className={`rounded-md border p-3 text-sm ${styles.container}`}
    >
      {/* Never colour-only: the tone is stated in text for screen readers. */}
      <span className="sr-only">{styles.label}: </span>
      {title && <p className="font-semibold">{title}</p>}
      <div>{children}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
