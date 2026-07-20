import type { ReactNode } from "react";

/**
 * A scroll container plus table primitives.
 *
 * Wide tables scroll horizontally inside their own region rather than forcing
 * the page to scroll. The region is focusable and labelled so it can be
 * reached and scrolled with the keyboard alone.
 */
export function TableScroll({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className="overflow-x-auto rounded-md border border-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700"
    >
      {children}
    </div>
  );
}

export function Table({
  children,
  caption,
}: {
  children: ReactNode;
  /** Visually hidden but announced, so every table has a name. */
  caption: string;
}) {
  return (
    <table className="w-full border-collapse text-left text-sm">
      <caption className="sr-only">{caption}</caption>
      {children}
    </table>
  );
}

export function Th({
  children,
  numeric = false,
  scope = "col",
}: {
  children: ReactNode;
  numeric?: boolean;
  scope?: "col" | "row";
}) {
  return (
    <th
      scope={scope}
      className={`sticky top-0 whitespace-nowrap bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200 ${
        numeric ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  numeric = false,
  wrap = false,
}: {
  children: ReactNode;
  numeric?: boolean;
  wrap?: boolean;
}) {
  return (
    <td
      className={`border-t border-slate-200 px-3 py-1.5 align-top dark:border-slate-700 ${
        numeric ? "text-right tabular-nums" : "text-left"
      } ${wrap ? "break-words" : "whitespace-nowrap"}`}
    >
      {children}
    </td>
  );
}
