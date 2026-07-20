import type { ReactNode } from "react";

type Tone = "neutral" | "info" | "warning" | "success";

const TONES: Record<Tone, string> = {
  neutral:
    "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  info: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-100",
  warning:
    "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  success:
    "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}
