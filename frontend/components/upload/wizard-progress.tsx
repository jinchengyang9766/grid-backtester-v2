import { VISIBLE_STEPS, visibleStepIndex, type WizardStep } from "@/lib/datasets/wizard-state";

/**
 * Step indicator. The current step is stated in text ("Step 2 of 5: Columns")
 * as well as shown visually, so progress never depends on colour alone.
 */
export function WizardProgress({ step }: { step: WizardStep }) {
  const currentIndex = visibleStepIndex(step);
  const current = VISIBLE_STEPS[currentIndex];

  return (
    <nav aria-label="Upload progress" className="mb-6">
      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
        Step {currentIndex + 1} of {VISIBLE_STEPS.length}: {current.label}
        {step === "DETECTING" && " — reading file"}
      </p>
      <ol className="mt-2 flex flex-wrap gap-1.5">
        {VISIBLE_STEPS.map((entry, index) => {
          const state =
            index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming";
          return (
            <li key={entry.step} className="flex-1 basis-24">
              <div
                aria-current={state === "current" ? "step" : undefined}
                className={`rounded-md border px-2 py-1.5 text-xs ${
                  state === "current"
                    ? "border-sky-700 bg-sky-50 font-semibold text-sky-900 dark:bg-sky-950 dark:text-sky-100"
                    : state === "done"
                      ? "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                      : "border-dashed border-slate-300 text-slate-500 dark:border-slate-700 dark:text-slate-400"
                }`}
              >
                {/* Text marker, not just a colour, for each state. */}
                <span className="block">
                  {state === "done" ? "Done" : state === "current" ? "Current" : "To do"}
                </span>
                <span className="block font-medium">{entry.label}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
