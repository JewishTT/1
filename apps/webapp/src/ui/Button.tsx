import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type ButtonVariant = "default" | "primary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Optional leading glyph from the UI 2.0 icon set. */
  icon?: IconName;
  iconAfter?: IconName;
  children?: ReactNode;
}

/**
 * Button (§60).
 *
 * Callers: AppShell top bar (pause/resume, theme, density), ContextInspector
 * section actions, Drawer/Palette close affordances, workspace toolbar.
 *
 * Hierarchy is size + weight + surface level. There is no glow, no gradient,
 * no scale-on-hover: hover changes the border and the text colour only.
 */
export function Button({
  variant = "default",
  size = "md",
  icon,
  iconAfter,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const content = (
    <>
      {icon ? <Icon name={icon} size={size === "sm" ? 12 : 14} /> : null}
      {children != null ? <span className="ui-btn-label">{children}</span> : null}
      {iconAfter ? <Icon name={iconAfter} size={size === "sm" ? 12 : 14} /> : null}
    </>
  );

  return (
    <button
      type={type}
      className="ui-btn"
      data-variant={variant}
      data-size={size}
      data-icon-only={children == null && (icon != null || iconAfter != null) ? "true" : undefined}
      {...rest}
    >
      {content}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "aria-label"> {
  icon: IconName;
  /** Mandatory: an icon-only control has no visible text, so it must name itself (§67). */
  label: string;
  size?: ButtonSize;
  variant?: ButtonVariant;
  /** Position hint for the paired Tooltip; the tooltip is optional, the label is not. */
  tooltipPlacement?: "top" | "right" | "bottom" | "left";
}

/**
 * IconButton (§60, §59).
 *
 * `label` is required and becomes both the accessible name and the tooltip
 * text. The glyph is never the only carrier of meaning.
 *
 * Callers: shell rail toggles, top bar (theme / density / palette),
 * inspector section collapse, drawer and palette close.
 */
export function IconButton({
  icon,
  label,
  size = "md",
  variant = "ghost",
  type = "button",
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      className="ui-btn ui-icon-btn"
      aria-label={label}
      title={label}
      data-variant={variant}
      data-size={size}
      {...rest}
    >
      <Icon name={icon} size={size === "sm" ? 12 : 14} />
    </button>
  );
}