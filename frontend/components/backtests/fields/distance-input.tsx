"use client";

import { DecimalInput } from "@/components/backtests/fields/decimal-input";
import { FormField } from "@/components/ui/form-field";
import { VALUE_MODES, type ValueMode } from "@/lib/api/backtest-types";
import type { ValueFormState } from "@/lib/backtests/configuration-state";
import { VALUE_MODE_LABELS } from "@/lib/backtests/display";

export interface DistanceInputProps {
  idPrefix: string;
  label: string;
  description: string;
  block: ValueFormState;
  valueError?: string;
  disabled?: boolean;
  onChange: (block: ValueFormState) => void;
}

/**
 * A mode + value pair (A distance, C distance, grid step).
 *
 * Switching the mode never rewrites the entered number: 0.05 means "0.05
 * currency units" under FIXED and "5% of the baseline" under PERCENT, and
 * silently converting between them would change the user's intent.
 */
export function DistanceInput({
  idPrefix,
  label,
  description,
  block,
  valueError,
  disabled,
  onChange,
}: DistanceInputProps) {
  const modeId = `${idPrefix}-mode`;
  const valueId = `${idPrefix}-value`;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <FormField id={modeId} label={`${label} mode`}>
        {(aria) => (
          <select
            {...aria}
            value={block.mode}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...block, mode: event.target.value as ValueMode })
            }
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-600 disabled:bg-slate-100 dark:border-slate-600 dark:bg-slate-900 dark:disabled:bg-slate-800"
          >
            {VALUE_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {VALUE_MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        )}
      </FormField>

      <DecimalInput
        id={valueId}
        label={label}
        description={description}
        error={valueError}
        value={block.value}
        disabled={disabled}
        onChange={(value) => onChange({ ...block, value })}
      />
    </div>
  );
}
