import { forwardRef, useId, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";

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

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "className"> {
  /** Visible label. Rendered above the control; placeholders are not labels. */
  label?: string;
  /** Render copyable context, queries or raw text in the monospace face. */
  mono?: boolean;
  hint?: string;
}

/** Multiline text input with the same labelling, token and focus contract as Input. */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, mono, id, ...rest },
  ref,
) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const control = (
    <textarea
      ref={ref}
      id={controlId}
      className="ui-textarea"
      data-mono={mono ? "true" : undefined}
      aria-describedby={hintId}
      {...rest}
    />
  );

  if (!label && !hint) return control;

  return (
    <span className="ui-field">
      {label ? <label className="ui-field-label" htmlFor={controlId}>{label}</label> : null}
      {control}
      {hint ? <span className="ui-field-hint" id={hintId}>{hint}</span> : null}
    </span>
  );
});

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "type"> {
  label: string;
  hint?: string;
}

/** Checkbox with a visible label and optional associated hint. */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, hint, id, ...rest },
  ref,
) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;

  return (
    <span className="ui-check-field">
      <label className="ui-check" htmlFor={controlId}>
        <input ref={ref} id={controlId} type="checkbox" aria-describedby={hintId} {...rest} />
        <span className="ui-check-label">{label}</span>
      </label>
      {hint ? <span className="ui-field-hint" id={hintId}>{hint}</span> : null}
    </span>
  );
});


export interface RadioOption<T extends string = string> {
  value: T;
  label: string;
  description?: string;
  disabled?: boolean;
}

export interface RadioGroupProps<T extends string = string> {
  /** Visible group name, rendered as a legend (not a placeholder). */
  label: string;
  /** Controlled selected value. */
  value: T;
  options: ReadonlyArray<RadioOption<T>>;
  onValueChange: (value: T) => void;
  hint?: string;
  name?: string;
  orientation?: "horizontal" | "vertical";
  disabled?: boolean;
  required?: boolean;
  id?: string;
}

/**
 * RadioGroup. Native radio inputs keep browser keyboard behavior, while the
 * shared field contract owns labels, descriptions, disabled state and layout.
 */
export function RadioGroup<T extends string = string>({
  label,
  value,
  options,
  onValueChange,
  hint,
  name,
  orientation = "vertical",
  disabled = false,
  required = false,
  id,
}: RadioGroupProps<T>) {
  const generatedId = useId();
  const groupId = id ?? generatedId;
  const hintId = hint ? `${groupId}-hint` : undefined;
  const groupName = name ?? groupId;

  return (
    <fieldset
      className="ui-radio-group"
      data-orientation={orientation}
      disabled={disabled}
      aria-describedby={hintId}
      data-testid={id ? `${id}-group` : undefined}
    >
      <legend className="ui-field-label">{label}</legend>
      <div className="ui-radio-options">
        {options.map((option) => (
          <label className="ui-radio" key={option.value}>
            <input
              type="radio"
              name={groupName}
              value={option.value}
              checked={value === option.value}
              disabled={disabled || option.disabled}
              required={required}
              onChange={() => onValueChange(option.value)}
            />
            <span className="ui-radio-copy">
              <span className="ui-radio-label">{option.label}</span>
              {option.description ? <span className="ui-radio-description">{option.description}</span> : null}
            </span>
          </label>
        ))}
      </div>
      {hint ? <span className="ui-field-hint" id={hintId}>{hint}</span> : null}
    </fieldset>
  );
}

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