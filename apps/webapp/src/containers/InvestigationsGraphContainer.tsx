import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { GraphCanvas } from "../graph/GraphCanvas";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, LoadingView } from "../ui/Feedback";
import { api, type InvestigationView } from "../lib/api";
import { entityProjectionKey, findingsKey } from "../lib/queryKeys";
import { usePipelineStream } from "../lib/stream";

/**
 * Investigations — the graph, not a list of things to click through.
 *
 * This used to be a heading, a text field and a Create button, with the real work on a
 * separate tab called Intel Board: two homes for one job, and the empty one owned the word
 * "investigations". That is now inverted. An investigation in this platform is a graph, so
 * the canvas is the surface you land on, and the list is the thing you use to *narrow* it.
 *
 * The scope switch is the whole point and it is a filter, not a navigation. `All
 * investigations` is the tenant's graph -- the same canvas, no scope -- and choosing one
 * narrows it to that investigation without leaving the graph. That is the difference between
 * a scope and a destination: a destination is somewhere you go and come back from; a scope is
 * a lens you put down and pick up.
 *
 * No investigation is ever opened by leaving this page. Opening one goes to its workspace,
 * where the graph is already the default view -- so "investigations" and "this
 * investigation" are the same surface at two scopes, not two screens.
 *
 * TWO THINGS THIS FILE EXISTS TO KEEP ALIVE, both of which were dead when it was written:
 *
 *   1. **Reactivity.** The graph is a projection of records the pipeline keeps rewriting, so
 *      it is only correct if it re-reads them. Intel Board was the only subscriber on this
 *      surface and it pushed events into a local feed list; when it was deleted, the canvas
 *      went stale until someone hit reload. The subscription now lives here and invalidates
 *      the two cache entries the graph actually reads -- see `refreshGraph`.
 *   2. **A way in.** An investigation with no entities is not an empty investigation, it is
 *      an unanswered question, and the only way to answer it used to be knowing the
 *      `POST /entities` body by heart. `seedFromText` takes what an analyst already has (a
 *      domain, a name, a list) and materialises one entity per subject.
 */

/** Subjects are split on hard breaks only — a name may legitimately contain spaces. */
function splitSubjects(text: string): string[] {
  const seen = new Map<string, string>();
  for (const raw of text.split(/[\n,;]+/)) {
    const subject = raw.trim();
    if (subject === "") continue;
    // Case-insensitive dedupe: a list that repeats a subject must not mint two entities
    // that the catalog then has to decide are the same one.
    const key = subject.toLowerCase();
    if (!seen.has(key)) seen.set(key, subject);
  }
  return [...seen.values()];
}

/**
 * A paste is not a plan. Pasted input arrives as one block of text, so this cap is the only
 * thing standing between a clipboard accident and one HTTP request per line; overflow is
 * reported rather than silently dropped.
 */
const MAX_SEED_SUBJECTS = 25;

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function InvestigationsGraphContainer() {
  const queryClient = useQueryClient();
  const seedInputRef = useRef<HTMLTextAreaElement>(null);

  const [items, setItems] = useState<InvestigationView[]>([]);
  const [scope, setScope] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [seed, setSeed] = useState("");
  const [seedText, setSeedText] = useState("");
  const [seedNote, setSeedNote] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [lastEvent, setLastEvent] = useState<string | null>(null);

  /**
   * `showLoading` is false for background refreshes. Flipping `loading` swaps the canvas for
   * a `LoadingView`, so a pipeline event arriving every few hundred milliseconds would
   * strobe the whole graph — the loop would be alive and the screen would still be unusable.
   */
  const load = useCallback(async (showLoading: boolean) => {
    if (showLoading) setLoading(true);
    try {
      setItems((await api.listInvestigations()).investigations);
      setError(null);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  /**
   * Drop the cached projection so the graph re-reads it.
   *
   * `/entities/graph` and `/findings` are tenant-wide — neither takes an investigation id —
   * so one payload backs every scope: an event about any investigation makes both the
   * selected scope's entry and the tenant entry stale. Those two are the only entries this
   * screen can be showing, and the same keys every other surface reads, so invalidating them
   * here refreshes the workspace's graph, timeline and evidence views for free.
   */
  const refreshGraph = useCallback(() => {
    for (const id of new Set([scope, null])) {
      void queryClient.invalidateQueries({ queryKey: entityProjectionKey(id) });
      void queryClient.invalidateQueries({ queryKey: findingsKey(id) });
    }
  }, [queryClient, scope]);

  usePipelineStream((event) => {
    setLastEvent(event.event);
    refreshGraph();
    // The scope switch reads /investigations, which only a pipeline advance can move.
    // An `entity.updated` storm would otherwise re-list the tenant on every record.
    if (event.event === "pipeline.advance") void load(false);
  });

  const create = async () => {
    if (!name.trim()) return;
    try {
      const created = await api.createInvestigation({ name: name.trim() });
      setName("");
      await load(false);
      // Land on the graph, not on a list: a new investigation is only interesting once it
      // is something you can look at.
      setScope(created.investigation_id ?? null);
    } catch (e) {
      setError(messageOf(e));
    }
  };

  // The API takes `canonical_identity`, not `canonical_name`: an entity is addressed by
  // the thing it *is* rather than by a label, and the label is only how we show it.
  const createSubject = (subject: string) =>
    api.createEntity({ canonical_identity: { name: subject }, label: subject });

  const addSeed = async () => {
    if (!seed.trim()) return;
    setError(null);
    try {
      await createSubject(seed.trim());
      setSeed("");
      // Adding an entity that nothing re-reads is the manual half of the loop this screen
      // is supposed to have closed.
      refreshGraph();
    } catch (e) {
      setError(messageOf(e));
    }
  };

  /**
   * Free text in, one entity per subject out.
   *
   * Deliberately `createEntity` per subject rather than one bulk call: there is no bulk
   * endpoint, and inventing one would put a route in the platform that nothing else serves.
   * Failures are collected rather than short-circuiting, so a list that is partly wrong
   * still lands the part that was right and says which part was not.
   */
  const seedFromText = async () => {
    const subjects = splitSubjects(seedText);
    if (subjects.length === 0) return;
    setSeeding(true);
    setError(null);

    const admitted = subjects.slice(0, MAX_SEED_SUBJECTS);
    const refused: string[] = [];
    let created = 0;
    try {
      for (const subject of admitted) {
        try {
          await createSubject(subject);
          created += 1;
        } catch (e) {
          refused.push(`${subject}: ${messageOf(e)}`);
        }
      }
    } finally {
      setSeeding(false);
    }

    const truncated = subjects.length - admitted.length;
    const parts = [`seeded ${created} subject${created === 1 ? "" : "s"}`];
    if (truncated > 0)
      parts.push(`${truncated} beyond the ${MAX_SEED_SUBJECTS}-subject cap were not sent`);
    if (refused.length > 0) parts.push(`refused — ${refused.join("; ")}`);
    setSeedNote(parts.join(" · "));

    if (refused.length === 0) setSeedText("");
    // Seeding writes entities, not investigations: the scope list is unchanged, but the
    // projection behind it is not.
    refreshGraph();
  };

  const scopeLabel = scope
    ? (items.find((i) => i.investigation_id === scope)?.name ?? scope)
    : "all investigations";

  return (
    // The same flex-column the investigation workspace uses. Wrapping the canvas in a
    // `.panel` instead is what made it a third of the screen with dead space beside it:
    // a bordered box sizes to its content, and a graph sized to its content is a postage
    // stamp. `flex: 1` on the body is the whole difference between a canvas and a panel.
    <div className="ui-workspace" data-testid="investigations-page">
      <div className="ui-canvas-head">
        <span className="ui-pane-title">Investigations</span>
        <span className="status-chip" data-testid="investigation-scope-label">
          {scopeLabel}
        </span>
        {/* The loop, stated rather than implied: which pipeline event last landed here. */}
        <Badge tone={lastEvent === null ? "neutral" : "accent"} testId="investigations-last-event">
          {lastEvent === null ? "pipeline idle" : `pipeline · ${lastEvent}`}
        </Badge>
        <div className="ui-graph-toolbar-grow" />
        {scope && (
          <Link className="ui-rail-hint" to={`/investigations/${scope}`}>
            open workspace
          </Link>
        )}
      </div>

      <div className="ui-canvas-head-meta">
        <div className="chip-row" data-testid="investigation-scope">
          <button
            type="button"
            className={`btn btn-sm${scope === null ? " btn-primary" : ""}`}
            onClick={() => setScope(null)}
            data-testid="scope-all"
          >
            All investigations
          </button>
          {items.map((item) => (
            <button
              key={item.investigation_id}
              type="button"
              className={`btn btn-sm${scope === item.investigation_id ? " btn-primary" : ""}`}
              onClick={() => setScope(item.investigation_id)}
              data-testid={`scope-${item.investigation_id}`}
            >
              {item.name}
            </button>
          ))}
          <input
            data-testid="new-investigation-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="new investigation"
            aria-label="New investigation name"
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => void create()}
            disabled={name.trim() === ""}
            data-testid="create-investigation"
          >
            Create
          </button>
        </div>
        <div className="chip-row" data-testid="entity-seed">
          <input
            data-testid="new-entity-seed"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            placeholder="new entity to add to the graph"
            aria-label="New entity"
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => void addSeed()}
            disabled={seed.trim() === ""}
            data-testid="create-entity"
          >
            Add entity
          </button>
        </div>

        {/* The way in: one field for whatever the analyst already has — a domain, a name,
            a list — instead of one field per subject. A `textarea`, not an `Input`: the
            HTML value-sanitization algorithm strips newlines from a single-line control,
            so a pasted newline-separated list would arrive as one run-together subject.
            Same bare-control convention as the fields above it (TDAPanel's series box). */}
        <div className="chip-row" data-testid="seed-from-text">
          <span className="op-label">seed from text</span>
          <textarea
            ref={seedInputRef}
            rows={2}
            data-testid="seed-text"
            value={seedText}
            onChange={(e) => setSeedText(e.target.value)}
            placeholder="example.com, ACME Holdings, 203.0.113.7"
            aria-label="Subjects to seed into the graph"
            disabled={seeding}
          />
          <Button
            variant="primary"
            size="sm"
            onClick={() => void seedFromText()}
            disabled={seeding || seedText.trim() === ""}
            data-testid="seed-submit"
          >
            {seeding ? "Seeding…" : "Seed from text"}
          </Button>
        </div>

        {seedNote && (
          <p className="panel-note" data-testid="seed-note">
            {seedNote}
          </p>
        )}

        {error && (
          <p className="panel-note" data-testid="error-view">
            {error}
          </p>
        )}
      </div>

      <div className="ui-canvas-body" data-view="graph">
        {loading ? (
          <LoadingView message="Loading investigations…" />
        ) : (
          <>
            <GraphCanvas investigationId={scope} />
            {items.length === 0 ? (
              // A tenant with no investigations still has a graph: it has no subjects yet.
              // Naming the next action beats leaving the canvas placeholder as the only
              // thing on screen, because it asks for an investigation this screen cannot
              // create on the analyst's behalf.
              <EmptyState
                icon="view-graph"
                title="No investigations yet"
                description="Name one, or seed the subjects you already have and let the graph build from them."
                action={
                  <Button
                    size="sm"
                    onClick={() => seedInputRef.current?.focus()}
                    data-testid="empty-seed-focus"
                  >
                    Seed subjects
                  </Button>
                }
                testId="investigations-empty"
              />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
