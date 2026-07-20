import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  /** Shows a pending label and blocks further clicks. */
  pending?: boolean;
  pendingLabel?: string;
}

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm " +
  "font-medium transition-colors " +
  // Always-visible keyboard focus.
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-sky-700 text-white hover:bg-sky-800 disabled:hover:bg-sky-700",
  secondary:
    "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 " +
    "dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700",
  ghost:
    "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800",
};

export function Button({
  variant = "primary",
  pending = false,
  pendingLabel,
  disabled,
  className = "",
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      // A pending action is disabled, so a second click cannot submit again.
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={`${BASE} ${VARIANTS[variant]} ${className}`}
      {...props}
    >
      {pending && (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
        />
      )}
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
