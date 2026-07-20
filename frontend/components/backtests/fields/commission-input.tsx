"use client";

import { DecimalInput } from "@/components/backtests/fields/decimal-input";
import type { CommissionFormState } from "@/lib/backtests/configuration-state";

export interface CommissionInputProps {
  idPrefix: string;
  legend: string;
  commission: CommissionFormState;
  errors: Record<string, string>;
  errorPrefix: string;
  disabled?: boolean;
  onChange: (commission: CommissionFormState) => void;
}

function Toggle({
  id,
  label,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 rounded border-slate-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
      />
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
    </div>
  );
}

/**
 * One side's commission: rate, minimum, and fixed components, each with its
 * own enable flag. All six fields are always submitted — the engine reads the
 * flags to decide which components apply.
 */
export function CommissionInputGroup({
  idPrefix,
  legend,
  commission,
  errors,
  errorPrefix,
  disabled,
  onChange,
}: CommissionInputProps) {
  return (
    <fieldset className="rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <legend className="px-1 text-sm font-semibold">{legend}</legend>

      <div className="space-y-4">
        <div className="space-y-2">
          <Toggle
            id={`${idPrefix}-rate-enabled`}
            label="Percentage rate"
            checked={commission.rate_enabled}
            disabled={disabled}
            onChange={(rate_enabled) => onChange({ ...commission, rate_enabled })}
          />
          <DecimalInput
            id={`${idPrefix}-rate`}
            label="Rate"
            description="A decimal fraction of the trade value: 0.0003 is 0.03%."
            error={errors[`${errorPrefix}.rate`]}
            value={commission.rate}
            disabled={disabled || !commission.rate_enabled}
            onChange={(rate) => onChange({ ...commission, rate })}
          />
        </div>

        <div className="space-y-2">
          <Toggle
            id={`${idPrefix}-minimum-enabled`}
            label="Minimum charge"
            checked={commission.minimum_enabled}
            disabled={disabled}
            onChange={(minimum_enabled) => onChange({ ...commission, minimum_enabled })}
          />
          <DecimalInput
            id={`${idPrefix}-minimum`}
            label="Minimum"
            description="Charged when the rate produces less than this amount."
            error={errors[`${errorPrefix}.minimum`]}
            value={commission.minimum}
            disabled={disabled || !commission.minimum_enabled}
            onChange={(minimum) => onChange({ ...commission, minimum })}
          />
        </div>

        <div className="space-y-2">
          <Toggle
            id={`${idPrefix}-fixed-enabled`}
            label="Fixed fee"
            checked={commission.fixed_enabled}
            disabled={disabled}
            onChange={(fixed_enabled) => onChange({ ...commission, fixed_enabled })}
          />
          <DecimalInput
            id={`${idPrefix}-fixed`}
            label="Fixed fee"
            description="A flat amount added to every trade on this side."
            error={errors[`${errorPrefix}.fixed`]}
            value={commission.fixed}
            disabled={disabled || !commission.fixed_enabled}
            onChange={(fixed) => onChange({ ...commission, fixed })}
          />
        </div>
      </div>
    </fieldset>
  );
}
