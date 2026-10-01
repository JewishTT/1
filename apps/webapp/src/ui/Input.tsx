import { forwardRef, useId, type InputHTMLAttributes, type SelectHTMLAttributes, type ReactNode } from "react";

import { Icon } from "./Icon";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "className"> {
  /** Visible label. Rendered above the control, never a placeholder-only label (§67). */
  label?: string;
  /** Static adornment rendered inside the control's left edge (e.g. a search glyph). */
  adornment?: ReactNode;
  /** Mono the value: use for anything the analyst types as an id, digest or query. */
  mono?: boolean;
  hint?: string;
}

/**
 * Input (§60).
 *
 * Callers: CommandPalette query field, workspace left-rail filter, view
 * toolbars, inspector inline filters.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, adornment, mono, hint, id, ...rest },
  ref,
) {
  // A label without `htmlFor` associates with nothing, which is worse than no
  // label: screen readers announce it as a stray string. So a labelled control
  // always gets an id (§67).
  const generatedId = useId();
  const controlId = id ?? generatedId;

  const control = (
    <span className="ui-input-wrap" data-mono={mono ? "true" : undefined}>
      {adornment ? (
        <span className="ui-input-adornment" aria-hidden="true">
          {adornment}
        </span>
      ) : null}
      <input ref={ref} id={controlId} className="ui-input" {...rest} />
    </span>
  );

  if (!label && !hint) return control;

  return (
    <span className="ui-field">
      {label ? (
        <label className="ui-field-label" htmlFor={controlId}>
          {label}
        </label>
      ) : null}
      {control}
      {hint ? <span className="ui-field-hint">{hint}</span> : null}
    </span>
  );
});

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
}

export interface SelectProps<T extends string = string>
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "className" | "onChange" | "value"> {
  label?: string;
  value: T;
  options: ReadonlyArray<SelectOption<T>>;
  onValueChange: (value: T) => void;
  hint?: string;
}

/**
 * Select (§60). Controlled; a native element so keyboard and mobile behaviour
 * is the platform's, not ours.
 *
 * Callers: CommandPalette scope filter, ContextInspector status filters,
 * left-rail kind filter.
 */
export function Select<T extends string = string>({
  label,
  value,
  options,
  onValueChange,
  hint,
  id,
  ...rest
}: SelectProps<T>) {
  // A label without `htmlFor` associates with nothing, which is worse than no
  // label at all — screen readers announce it as a stray string. So when a
  // label is present the control always gets an id (§67).
  const generatedId = useId();
  const controlId = id ?? generatedId;

  const control = (
    <span className="ui-select-wrap">
      <select
        id={controlId}
        className="ui-select"
        value={value}
        onChange={(event) => onValueChange(event.target.value as T)}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <span className="ui-select-chevron" aria-hidden="true">
        <Icon name="chevron-down" size={12} />
      </span>
    </span>
  );

  if (!label && !hint) return control;

  return (
    <span className="ui-field">
      {label ? (
        <label className="ui-field-label" htmlFor={controlId}>
          {label}
        </label>
      ) : null}
      {control}
      {hint ? <span className="ui-field-hint">{hint}</span> : null}
    </span>
  );
}