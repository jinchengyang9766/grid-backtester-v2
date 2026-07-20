import type { InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

const BASE =
  "block w-full rounded-md border px-3 py-2.5 text-sm text-slate-900 " +
  "placeholder:text-slate-400 " +
  "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 " +
  "disabled:cursor-not-allowed disabled:bg-slate-100 " +
  "dark:bg-slate-900 dark:text-slate-100 dark:disabled:bg-slate-800";

export function Input({ invalid = false, className = "", ...props }: InputProps) {
  const border = invalid
    ? "border-red-600 dark:border-red-500"
    : "border-slate-300 dark:border-slate-600";
  return (
    <input
      // Communicated to assistive tech, not by colour alone.
      aria-invalid={invalid || undefined}
      className={`${BASE} ${border} ${className}`}
      {...props}
    />
  );
}
