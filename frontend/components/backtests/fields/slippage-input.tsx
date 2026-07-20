"use client";

import { DistanceInput } from "@/components/backtests/fields/distance-input";
import type { SlippageFormState } from "@/lib/backtests/configuration-state";

export interface SlippageInputProps {
  slippage: SlippageFormState;
  errors: Record<string, string>;
  disabled?: boolean;
  onChange: (slippage: SlippageFormState) => void;
}

/**
 * Shared or per-side slippage.
 *
 * Both shapes are kept in UI state so toggling does not lose what was typed,
 * but only the active one is serialized — the backend rejects an object that
 * carries both a top-level value and buy/sell overrides.
 */
export function SlippageInputGroup({
  slippage,
  errors,
  disabled,
  onChange,
}: SlippageInputProps) {
  return (
    <fieldset className="space-y-4">
      <legend className="text-sm font-semibold">Slippage</legend>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Apply slippage</legend>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <input
              id="slippage-shared"
              type="radio"
              name="slippage-mode"
              checked={slippage.shared}
              disabled={disabled}
              onChange={() => onChange({ ...slippage, shared: true })}
              className="size-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            />
            <label htmlFor="slippage-shared" className="text-sm">
              Same for buys and sells
            </label>
          </div>
          <div className="flex items-center gap-2">
            <input
              id="slippage-separate"
              type="radio"
              name="slippage-mode"
              checked={!slippage.shared}
              disabled={disabled}
              onChange={() => onChange({ ...slippage, shared: false })}
              className="size-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            />
            <label htmlFor="slippage-separate" className="text-sm">
              Separate buy and sell
            </label>
          </div>
        </div>
      </fieldset>

      {slippage.shared ? (
        <DistanceInput
          idPrefix="slippage-value"
          label="Slippage"
          description="Applied to every execution price on both sides."
          block={slippage.sharedValue}
          valueError={errors["configuration.slippage.value"]}
          disabled={disabled}
          onChange={(sharedValue) => onChange({ ...slippage, sharedValue })}
        />
      ) : (
        <div className="space-y-4">
          <DistanceInput
            idPrefix="slippage-buy"
            label="Buy slippage"
            description="Applied to buy execution prices."
            block={slippage.buy}
            valueError={errors["configuration.slippage.buy.value"]}
            disabled={disabled}
            onChange={(buy) => onChange({ ...slippage, buy })}
          />
          <DistanceInput
            idPrefix="slippage-sell"
            label="Sell slippage"
            description="Applied to sell execution prices."
            block={slippage.sell}
            valueError={errors["configuration.slippage.sell.value"]}
            disabled={disabled}
            onChange={(sell) => onChange({ ...slippage, sell })}
          />
        </div>
      )}
    </fieldset>
  );
}
