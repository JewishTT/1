import { useId, type HTMLAttributes, type ReactNode } from "react";

export type PanelVariant = "default" | "flat" | "raised";

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "className" | "title"> {
  /** Concise section heading; renders an accessible heading association. */
  title?: string;
  /** Optional small uppercase context label. */
  eyebrow?: string;
  description?: ReactNode;
  actions?: ReactNode;
  variant?: PanelVariant;
  children: ReactNode;
  testId?: string;
}

/**
 * Panel (§60, §93). Shared, low-radius workbench surface.
 *
 * It owns surface hierarchy, header spacing, heading semantics and the
 * optional action slot. Domain sections still own their data and behavior.
 * No arbitrary className or inline color props: visual variation is semantic.
 */
export function Panel({
  title,
  eyebrow,
  description,
  actions,
  variant = "default",
  children,
  testId,
  ...rest
}: PanelProps) {
  const headingId = useId();
  const hasHeader = Boolean(title || eyebrow || description || actions);

  return (
    <section
      className="ui-panel"
      data-variant={variant}
      aria-labelledby={title ? headingId : undefined}
      data-testid={testId}
      {...rest}
    >
      {hasHeader ? (
        <header className="ui-panel-head">
          <div className="ui-panel-heading">
            {eyebrow ? <p className="ui-panel-eyebrow ui-meta">{eyebrow}</p> : null}
            {title ? <h2 className="ui-panel-title" id={headingId}>{title}</h2> : null}
            {description ? <div className="ui-panel-description">{description}</div> : null}
          </div>
          {actions ? <div className="ui-panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ui-panel-body">{children}</div>
    </section>
  );
}
