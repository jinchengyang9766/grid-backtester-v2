"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /**
   * Destructive dialogs still close on Escape (a cancel is always safe), but
   * never on a backdrop click, so a stray click cannot dismiss a confirmation
   * the user was reading.
   */
  dismissOnBackdrop?: boolean;
}

/**
 * A modal dialog built on native semantics rather than a component library:
 * labelled by its title, described by its body, focus moved in on open and
 * returned to the trigger on close, and Escape always cancels.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  dismissOnBackdrop = true,
}: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // Move focus into the dialog so the keyboard lands in the right place.
    const focusTarget =
      panelRef.current?.querySelector<HTMLElement>(
        "[data-autofocus], button, [href], input, select, textarea",
      ) ?? panelRef.current;
    focusTarget?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      // Keep Tab inside the dialog while it is open.
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      // Return focus to whatever opened the dialog.
      previouslyFocused.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-slate-900/50 p-4 sm:items-center">
      {/* Backdrop: a click target only, never the sole way to dismiss. */}
      <div
        aria-hidden="true"
        className="absolute inset-0"
        onClick={dismissOnBackdrop ? onClose : undefined}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className="relative w-full max-w-2xl rounded-lg bg-white p-5 shadow-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-slate-900"
      >
        <h2 id={titleId} className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {title}
        </h2>
        {description && (
          <p id={descriptionId} className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            {description}
          </p>
        )}
        <div className="mt-4 max-h-[60vh] overflow-y-auto">{children}</div>
        {footer && <div className="mt-5 flex flex-wrap justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
