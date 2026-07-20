"use client";

import { FormField } from "@/components/ui/form-field";
import { OHLC_PATH_MODES, type OhlcPathMode } from "@/lib/api/backtest-types";
import { PATH_MODE_HINTS, PATH_MODE_LABELS } from "@/lib/backtests/display";

export interface PathModeInputProps {
  /** The dataset's own data mode, which decides whether this applies at all. */
  dataMode: string;
  value: OhlcPathMode;
  disabled?: boolean;
  onChange: (mode: OhlcPathMode) => void;
}

/**
 * The intraday path assumption.
 *
 * A CLOSE_ONLY dataset has no high/low, so there is no path to choose and the
 * request sends null. Offering a choice there would imply the data contains
 * information it does not.
 */
export function PathModeInput({
  dataMode,
  value,
  disabled,
  onChange,
}: PathModeInputProps) {
  if (dataMode !== "OHLCV") {
    return (
      <fieldset className="space-y-2">
        <legend className="text-sm font-semibold">Intraday path assumption</legend>
        <p className="text-sm text-slate-700 dark:text-slate-300">
          This dataset is close-only, so it carries no intraday high or low.
          No path assumption applies and none is sent.
        </p>
      </fieldset>
    );
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-semibold">Intraday path assumption</legend>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Daily bars do not record the order in which the high and low occurred.
        This chooses what the engine assumes.
      </p>
      <FormField id="ohlc-path-mode" label="Path mode" description={PATH_MODE_HINTS[value]}>
        {(aria) => (
          <select
            {...aria}
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value as OhlcPathMode)}
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 disabled:bg-slate-100 dark:border-slate-600 dark:bg-slate-900 dark:disabled:bg-slate-800"
          >
            {OHLC_PATH_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {PATH_MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        )}
      </FormField>
    </fieldset>
  );
}
