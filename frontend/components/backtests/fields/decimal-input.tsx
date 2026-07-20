"use client";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";

export interface DecimalInputProps {
  id: string;
  label: string;
  description?: string;
  error?: string;
  value: string;
  disabled?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}

/**
 * A text input for a decimal string.
 *
 * Deliberately `type="text"` with `inputMode="decimal"`: a number input
 * exposes `valueAsNumber` semantics and lets browsers normalize or reformat
 * the entry, which would defeat keeping the exact typed string.
 */
export function DecimalInput({
  id,
  label,
  description,
  error,
  value,
  disabled,
  placeholder,
  onChange,
}: DecimalInputProps) {
  return (
    <FormField id={id} label={label} description={description} error={error}>
      {(aria) => (
        <Input
          {...aria}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          invalid={Boolean(error)}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </FormField>
  );
}

/** The same control for whole-number counts such as shares and lots. */
export function IntegerInput({
  id,
  label,
  description,
  error,
  value,
  disabled,
  onChange,
}: Omit<DecimalInputProps, "placeholder">) {
  return (
    <FormField id={id} label={label} description={description} error={error}>
      {(aria) => (
        <Input
          {...aria}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={disabled}
          invalid={Boolean(error)}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </FormField>
  );
}
