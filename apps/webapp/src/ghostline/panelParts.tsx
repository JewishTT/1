import type { ReactNode } from "react";

import { Badge, StatusDot } from "../ui/Badge";
import { ApiError } from "../lib/http";
import type { GlStatusWire } from "../lib/api";
import { toProviderRow, toRuntimeRow } from "./model";
import type { GlProviderRow, GlRefusal, GlRuntimeRow } from "./types";

/**
 * Shared furniture for the GhostLine surface (Feature 031).
 *
 * The one piece here that is not boilerplate is `Refusal`. GhostLine's calls fail
 * for two structurally different reasons and collapsing them into "error" would
 * teach an operator the wrong lesson:
 *
 * * **A gate refusal** (`RoEError` / `RosterError`, HTTP 409/422) means an
 *   authorisation question was answered "no". Retrying will not help; only a
 *   supervisor changing the sign-off will.
 * * **A setup gap** (HTTP 424) means something is not configured or not installed.
 *   It names the variable to set or the package to add, and it is the common case
 *   on a fresh deployment.
 *
 * So they render differently, and `classify` is the one place that decides which.
 */

export function GlShell({
  title,
  status,
  children,
  testId,
}: {
  title: string;
  status?: ReactNode;
  children: ReactNode;
  testId: string;
}) {
  return (
    <section className="ui-ci-panel" data-testid={testId}>
      <header className="ui-ci-panel-head">
        <span className="ui-pane-title">{title}</span>
        <span className="ui-id">tenant-wide · RoE-gated · not scoped to one investigation</span>
        {status}
      </header>
      {children}
    </section>
  );
}

export function Chip({
  label,
  tone = "neutral",
  title,
  testId,
}: {
  label: string;
  tone?: "accent" | "gold" | "danger" | "neutral" | "analytical" | "strong";
  title?: string;
  testId?: string;
}) {
  return (
    <Badge tone={tone} title={title} testId={testId}>
      {label}
    </Badge>
  );
}

/** A named absence: what is not served, and which endpoint would serve it. */
export function Missing({ items, testId }: { items: readonly string[]; testId: string }) {
  if (items.length === 0) return null;
  return (
    <ul className="ui-blockers" data-testid={testId}>
      {items.map((text) => (
        <li key={text} className="ui-blocker">
          <span className="ui-blocker-name">not served</span>
          <span className="ui-blocker-settled">{text}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Decide what kind of failure this is.
 *
 * The server's own `detail` carries the gate's code and rejected targets verbatim,
 * so the classification reads real facts off the response rather than guessing from
 * a message string.
 */
export function classify(err: unknown): GlRefusal {
  if (!(err instanceof ApiError)) {
    return { kind: "setup", reason: err instanceof Error ? err.message : String(err) };
  }
  const detail = err.detail;
  const code =
    detail && typeof detail === "object" && "error" in detail
      ? String((detail as { error: unknown }).error)
      : null;
  const reason =
    detail && typeof detail === "object" && "reason" in detail
      ? String((detail as { reason: unknown }).reason)
      : err.message;
  const rejected =
    detail && typeof detail === "object" && "rejected_targets" in detail
      ? (((detail as { rejected_targets: unknown }).rejected_targets as string[]) ?? [])
      : [];

  if (code === "RoEError" || code === "RosterError") {
    return { kind: "gate", code, reason, rejected };
  }
  if (code) return { kind: "setup", reason };
  if (err.status === 409 || err.status === 422) {
    // A gate refusal that arrived without its structured detail still belongs to the
    // gate: 409 and 422 are the gate's two codes and nothing else uses them here.
    return { kind: "gate", code: `HTTP ${err.status}`, reason, rejected };
  }
  return { kind: "setup", reason };
}

/**
 * Render a failure. The heading says which kind it is, because that is the first
 * thing an operator needs to know and the badge is how they learn it.
 */
export function Refusal({ refusal, testId }: { refusal: GlRefusal | null; testId: string }) {
  if (!refusal) return null;
  if (refusal.kind === "gate") {
    return (
      <div className="ui-gl-refusal" data-kind="gate" data-testid={testId}>
        <Chip label={`refused · ${refusal.code}`} tone="danger" />
        <span className="ui-gl-refusal-reason">{refusal.reason}</span>
        {refusal.rejected.length > 0 ? (
          <span className="ui-id" data-testid={`${testId}-rejected`}>
            rejected: {refusal.rejected.join(", ")}
          </span>
        ) : null}
      </div>
    );
  }
  const heading = refusal.kind === "absent" ? "not available" : "cannot run yet";
  return (
    <div className="ui-gl-refusal" data-kind={refusal.kind} data-testid={testId}>
      <Chip label={heading} tone="gold" />
      <span className="ui-gl-refusal-reason">{refusal.reason}</span>
    </div>
  );
}

/** Runtime state as a dot, using the department's closed status vocabulary. */
export function RuntimeDot({ runtime, testId }: { runtime: GlRuntimeRow; testId?: string }) {
  const label =
    runtime.state === "running"
      ? `running · ${runtime.voiceName ?? runtime.voiceId ?? "voice"}`
      : runtime.state === "blocked"
        ? `blocked · ${runtime.blockers.length} missing`
        : "stopped";
  const status =
    runtime.state === "running" ? "Running" : runtime.state === "blocked" ? "Blocked" : "Paused";
  return (
    <StatusDot status={status} label={label} live={runtime.state === "running"} testId={testId} />
  );
}

/** Provider readiness as a list: each row is a variable the operator either set or did not. */
export function ProviderList({
  providers,
  testId,
}: {
  providers: readonly GlProviderRow[];
  testId: string;
}) {
  return (
    <ul className="ui-gl-providers" data-testid={testId}>
      {providers.map((provider) => (
        <li key={provider.name} data-configured={provider.configured}>
          <StatusDot
            status={provider.status}
            label={provider.name}
            testId={`${testId}-${provider.name}`}
          />
          <span className="ui-gl-provider-detail">{provider.detail}</span>
          {provider.configured ? null : (
            <code className="ui-gl-env" data-testid={`${testId}-${provider.name}-env`}>
              {provider.envVar}
            </code>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Project a status payload into the rows the panels read. */
export function fromStatus(status: GlStatusWire): {
  providers: GlProviderRow[];
  runtime: GlRuntimeRow;
} {
  return {
    providers: status.providers.map(toProviderRow),
    runtime: toRuntimeRow(status.runtime),
  };
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="panel-note">{children}</p>;
}
