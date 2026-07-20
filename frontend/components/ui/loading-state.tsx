export interface LoadingStateProps {
  /** Announced and shown as text, not conveyed by the spinner alone. */
  label?: string;
  fullPage?: boolean;
}

export function LoadingState({
  label = "Loading…",
  fullPage = false,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        fullPage
          ? "flex min-h-[60vh] flex-col items-center justify-center gap-3"
          : "flex items-center gap-3 py-4"
      }
    >
      <span
        aria-hidden="true"
        className="size-5 animate-spin rounded-full border-2 border-slate-400 border-t-transparent motion-reduce:animate-none"
      />
      <p className="text-sm text-slate-600 dark:text-slate-400">{label}</p>
    </div>
  );
}
