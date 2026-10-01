import { useMemo } from "react";

import { Badge, StatusDot } from "../../ui/Badge";
import { Button, IconButton } from "../../ui/Button";
import { EmptyState, Skeleton } from "../../ui/Feedback";
import { Tooltip } from "../../ui/Overlay";
import { actionsForSelection, destinationForAction } from "../commands";
import { useWorkspace } from "../store";
import type { WorkspaceSelection } from "../types";
import { useInspectorModel } from "./useInspector";
import type { InspectorField, InspectorSection } from "./types";

/**
 * ContextInspector (§6, §19, §33, §34).
 *
 * The right pane. Object-driven: it renders whatever is selected, in the same
 * place, for every kind of object. Left context and this panel persist while
 * the centre canvas switches views — that persistence is the single-workstation
 * model (§24).
 *
 * It subscribes to three narrow slices (`selection`, `openInspectorSections`,
 * `secondarySelection`), never the whole store, so selecting a node does not
 * re-render the canvas (§68).
 */

/** Expand state is per-section, defaulted open for the first section only. */
function useSectionOpen(sectionId: string, index: number, hasStored: boolean): boolean {
  const stored = useWorkspace((state) => state.openInspectorSections[sectionId]);
  return hasStored ? Boolean(stored) : index === 0;
}

function FieldRow({
  field,
  onGoTo,
}: {
  field: InspectorField;
  onGoTo: (target: NonNullable<InspectorField["linkTo"]>) => void;
}) {
  const value = field.value;

  return (
    <div className="ui-insp-field" data-testid={`inspector-field-${field.key}`}>
      <span className="ui-insp-field-label">{field.label}</span>
      <span className="ui-insp-field-value" data-mono={field.mono ? "true" : undefined}>
        {value === null ? (
          // §99: an unreported value says so. A blank would read as "empty".
          <span className="ui-insp-unreported">not reported</span>
        ) : field.linkTo ? (
          <button
            type="button"
            className="ui-insp-link"
            onClick={() => onGoTo(field.linkTo as NonNullable<InspectorField["linkTo"]>)}
            title={`Open ${field.linkTo.kind} ${field.linkTo.id}`}
          >
            {String(value)}
          </button>
        ) : (
          String(value)
        )}
      </span>
    </div>
  );
}

function Section({
  section,
  index,
  onGoTo,
}: {
  section: InspectorSection;
  index: number;
  onGoTo: (target: NonNullable<InspectorField["linkTo"]>) => void;
}) {
  const hasStored = useWorkspace((state) => section.id in state.openInspectorSections);
  const open = useSectionOpen(section.id, index, hasStored);
  const toggle = useWorkspace((state) => state.toggleInspectorSection);

  return (
    <section className="ui-insp-section" data-section={section.id} data-testid={`inspector-section-${section.id}`}>
      <h3 className="ui-pane-title">
        <button
          type="button"
          className="ui-insp-section-toggle"
          aria-expanded={open}
          onClick={() => toggle(section.id)}
        >
          {section.title}
        </button>
      </h3>
      {open ? (
        <div className="ui-insp-section-body">
          {section.fields.map((field) => (
            <FieldRow key={field.key} field={field} onGoTo={onGoTo} />
          ))}
          {section.references && section.references.length > 0 ? (
            <div className="ui-insp-refs">
              {section.references.slice(0, 6).map((reference) => (
                <Button
                  key={`${reference.kind}:${reference.id}`}
                  size="sm"
                  onClick={() => onGoTo(reference)}
                  title={`Open ${reference.kind} ${reference.id}`}
                >
                  {reference.label ?? reference.id}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/**
 * §69: every major object offers a next step. Rendered as real buttons that
 * move the global selection, so the panel is never a dead end.
 */
function NextSteps({ selection }: { selection: WorkspaceSelection }) {
  // Selecting the *length*, not the array: `selectSecondaryIds` builds a fresh
  // array on every store read, so subscribing to it would re-render this
  // component on every unrelated store write — exactly the §68 failure the
  // selector-scoped subscriptions exist to prevent. The count is all this
  // component needs.
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);
  const actions = useMemo(
    () => actionsForSelection(selection, secondaryCount),
    [selection, secondaryCount],
  );
  const setView = useWorkspace((state) => state.setView);

  if (actions.length === 0) return null;

  return (
    <div className="ui-insp-next" data-testid="inspector-next">
      <span className="ui-pane-title">Next</span>
      <div className="ui-insp-next-list">
        {actions.map((action) => {
          const destination = destinationForAction(action.id);
          // An action with no declared destination is not rendered at all: a
          // button that cannot move the analyst anywhere is a dead end (§69).
          if (destination === null) return null;
          return (
            <Button key={action.id} size="sm" onClick={() => setView(destination)}>
              {action.label}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

export function ContextInspector() {
  const selection = useWorkspace((state) => state.selection);
  const select = useWorkspace((state) => state.select);
  const { model, loading, error } = useInspectorModel();

  if (!selection) {
    return (
      <aside className="ui-inspector ui-root" aria-label="Object inspector" data-testid="context-inspector">
        <EmptyState
          icon="view-objects"
          title="No object selected"
          description="Select an entity, observation, claim or finding. The selection is global: the graph, timeline and evidence views follow it."
          testId="inspector-empty"
        />
      </aside>
    );
  }

  return (
    <aside
      className="ui-inspector ui-root ui-scroll"
      aria-label="Object inspector"
      data-kind={model.kind ?? undefined}
      data-testid="context-inspector"
    >
      <header className="ui-inspector-head">
        <div className="ui-inspector-titles">
          <h2 className="ui-title ui-truncate" data-testid="inspector-title">
            {model.title ?? selection.id}
          </h2>
          {model.subtitle ? (
            <span className="ui-id ui-truncate" data-testid="inspector-subtitle">
              {model.subtitle}
            </span>
          ) : null}
        </div>
        <div className="ui-inspector-badges">
          {model.badges.map((badge) => (
            <Badge key={badge.label} tone={badge.tone} role="classification" testId={`inspector-badge-${badge.label}`}>
              {badge.label}
            </Badge>
          ))}
          <Tooltip content="Clear the global selection (Esc)">
            <IconButton icon="close" label="Clear selection" size="sm" onClick={() => select(null)} />
          </Tooltip>
        </div>
      </header>

      <div className="ui-inspector-body">
        {error != null ? (
          <div className="ui-inspector-error" role="alert" data-testid="inspector-error">
            <StatusDot status="Failed" label="Fetch failed" />
            <p className="ui-body">{error}</p>
          </div>
        ) : null}

        {loading ? <Skeleton rows={6} label="Loading object details" /> : null}

        {model.unavailable ? (
          <EmptyState
            size="sm"
            icon="view-evidence"
            title={`${model.kind ?? selection.kind} record not fetched`}
            description={`No record endpoint is wired for this object type yet. The selection is held, so it survives a view switch.`}
            testId="inspector-unavailable"
          />
        ) : null}

        {!loading && !model.unavailable
          ? model.sections.map((section, index) => (
              <Section key={section.id} section={section} index={index} onGoTo={(target) => select(target)} />
            ))
          : null}

        <NextSteps selection={selection} />
      </div>
    </aside>
  );
}