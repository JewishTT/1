import { useCallback, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export interface TabsItem<T extends string> {
  value: T;
  label: string;
  /** Optional glyph. The label always remains present — the icon is not the label (§59). */
  icon?: IconName;
  /** Optional single-key hint shown as the tab's shortcut badge (e.g. `G`). */
  shortcut?: string;
  disabled?: boolean;
}

export interface TabsProps<T extends string> {
  items: ReadonlyArray<TabsItem<T>>;
  value: T;
  onValueChange: (value: T) => void;
  /** Accessible name for the tablist, e.g. "workspace views". */
  label: string;
  /** `rail` is the vertical left-rail form; `bar` is the horizontal canvas switcher. */
  orientation?: "rail" | "bar";
}

/**
 * Tabs (§60). Two layouts, one component: the vertical left rail and the
 * horizontal view switcher in the canvas header.
 *
 * Roving tabindex + arrow/Home/End keys, per the WAI-ARIA tabs pattern (§67).
 *
 * Callers: AppShell left rail (global destinations), InvestigationWorkspace
 * canvas header (Overview / Graph / Objects / Evidence / Timeline /
 * Acquisition / Findings / Analysis — §4).
 */
export function Tabs<T extends string>({
  items,
  value,
  onValueChange,
  label,
  orientation = "rail",
}: TabsProps<T>) {
  const baseId = useId();
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const focusAt = useCallback((index: number) => {
    const item = items[(index + items.length) % items.length];
    if (!item || item.disabled) return;
    refs.current.get(item.value)?.focus();
  }, [items]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextKey = orientation === "rail" ? "ArrowDown" : "ArrowRight";
    const prevKey = orientation === "rail" ? "ArrowUp" : "ArrowLeft";
    if (event.key === nextKey) {
      event.preventDefault();
      focusAt(index + 1);
    } else if (event.key === prevKey) {
      event.preventDefault();
      focusAt(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusAt(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusAt(items.length - 1);
    }
  };

  // WAI-ARIA's aria-orientation only knows horizontal/vertical; our two
  // layouts map onto them directly (rail = vertical, bar = horizontal).
  const ariaOrientation = orientation === "rail" ? "vertical" : "horizontal";

  return (
    <div className="ui-tabs" role="tablist" aria-label={label} aria-orientation={ariaOrientation}>
      {items.map((item, index) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(node) => {
              if (node) refs.current.set(item.value, node);
              else refs.current.delete(item.value);
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${item.value}`}
            aria-selected={selected}
            aria-controls={`${baseId}-panel`}
            aria-disabled={item.disabled || undefined}
            disabled={item.disabled}
            tabIndex={selected ? 0 : -1}
            className="ui-tab"
            data-orientation={orientation}
            data-active={selected}
            data-testid={`tab-${item.value}`}
            onClick={() => onValueChange(item.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {item.icon ? <Icon name={item.icon} size={14} /> : null}
            <span className="ui-tab-label">{item.label}</span>
            {item.shortcut ? (
              <span className="ui-tab-shortcut" aria-hidden="true">
                {item.shortcut}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export interface TabPanelProps {
  /** Matches the tablist's `${baseId}-panel`; callers pass the shared panel id. */
  panelId: string;
  children: ReactNode;
}

/** Tab content surface. Separate from Tabs so both panes keep their own identity. */
export function TabPanel({ panelId, children }: TabPanelProps) {
  return (
    <div className="ui-tabpanel" id={panelId} role="tabpanel" tabIndex={-1}>
      {children}
    </div>
  );
}