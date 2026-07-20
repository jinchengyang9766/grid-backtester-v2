"use client";

import { useId, useRef, useState, type ReactNode } from "react";

export interface TabDefinition {
  id: string;
  label: string;
  render: () => ReactNode;
}

/**
 * A keyboard-operable tab list following the ARIA authoring pattern:
 * arrow keys move between tabs, Home/End jump to the ends, and only the
 * active tab is in the tab order.
 */
export function ResultTabs({ tabs }: { tabs: readonly TabDefinition[] }) {
  const baseId = useId();
  const [active, setActive] = useState(tabs[0]?.id ?? "");
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const activeIndex = Math.max(
    0,
    tabs.findIndex((tab) => tab.id === active),
  );

  function focusTab(index: number) {
    const target = tabs[(index + tabs.length) % tabs.length];
    setActive(target.id);
    refs.current.get(target.id)?.focus();
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTab(activeIndex + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTab(activeIndex - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTab(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTab(tabs.length - 1);
    }
  }

  const current = tabs[activeIndex];

  return (
    <div>
      <div
        role="tablist"
        aria-label="Result sections"
        onKeyDown={handleKeyDown}
        className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-700"
      >
        {tabs.map((tab) => {
          const selected = tab.id === current?.id;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                if (node) refs.current.set(tab.id, node);
                else refs.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              className={`rounded-t-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 ${
                selected
                  ? "border-b-2 border-sky-700 text-sky-900 dark:text-sky-100"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {current && (
        <div
          role="tabpanel"
          id={`${baseId}-panel-${current.id}`}
          aria-labelledby={`${baseId}-tab-${current.id}`}
          tabIndex={0}
          className="pt-5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        >
          {current.render()}
        </div>
      )}
    </div>
  );
}
