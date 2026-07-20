"use client";

import { DecimalInput } from "@/components/backtests/fields/decimal-input";

export interface TickSizeInputProps {
  enabled: boolean;
  value: string;
  error?: string;
  disabled?: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onValueChange: (value: string) => void;
}

/**
 * Tick-size normalization.
 *
 * When disabled the request carries `{ enabled: false, value: null }`. No
 * rounding happens in the browser: the engine applies tick normalization to
 * the grid, and doing it twice could disagree with the executed prices.
 */
export function TickSizeInput({
  enabled,
  value,
  error,
  disabled,
  onEnabledChange,
  onValueChange,
}: TickSizeInputProps) {
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-semibold">Tick size</legend>

      <div className="flex items-center gap-2">
        <input
          id="tick-size-enabled"
          type="checkbox"
          checked={enabled}
          disabled={disabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
          className="size-4 rounded border-slate-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        />
        <label htmlFor="tick-size-enabled" className="text-sm font-medium">
          Round grid levels to a tick size
        </label>
      </div>

      {enabled && (
        <DecimalInput
          id="tick-size-value"
          label="Tick size"
          description="The smallest price increment, for example 0.001. The engine applies this when it builds the grid."
          error={error}
          value={value}
          disabled={disabled}
          onChange={onValueChange}
        />
      )}

      {!enabled && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Grid levels are used exactly as calculated, with no tick rounding.
        </p>
      )}
    </fieldset>
  );
}
