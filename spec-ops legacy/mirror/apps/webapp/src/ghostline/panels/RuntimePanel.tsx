import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "../../ui/Button";
import { Input, Select } from "../../ui/Input";
import { api } from "../../lib/api";
import type { GlStatusWire, GlVoiceWire } from "../../lib/api";
import {
  Chip,
  classify,
  GlShell,
  Missing,
  ProviderList,
  Refusal,
  RuntimeDot,
  fromStatus,
} from "../panelParts";
import { dialReadiness } from "../model";
import type {
  GlPanel,
  GlPlaybookRow,
  GlProviderRow,
  GlRefusal,
  GlRuntimeRow,
  GlVoiceRow,
} from "../types";
import { toPlaybookRow, toVoiceRow } from "../model";

/**
 * Runtime panel — the donor's `serve` verb (Feature 031).
 *
 * Three things in one panel because they are one question: can an exercise run right
 * now, and if not, what is missing. The provider checklist is the answer to "what is
 * missing" — it is the donor's six credentials and tunnel, each with the variable that
 * sets it, rendered as a setup list rather than as a wall of errors. The composer is the
 * answer to "can it run": a voice and a playbook, which is exactly what the CLI's
 * `serve --voice-id X --playbook Y` takes.
 *
 * The donor's stage engine is reported separately from the live edges on purpose. The
 * engine — the 12-stage taxonomy, the playbook schema, the transition runner, the mu-law
 * codec, the Twilio frame protocol — runs inside this process today and is what makes
 * the Playbooks and Simulate panels real rather than mocked. The edges need packages
 * and credentials this environment does not carry, and they are named individually so
 * "Twilio is not installed" is never mistaken for "the donor is missing".
 */
export function RuntimePanel({ onNavigate }: { onNavigate?: (panel: GlPanel) => void }) {
  const [status, setStatus] = useState<GlStatusWire | null>(null);
  const [playbooks, setPlaybooks] = useState<GlPlaybookRow[]>([]);
  const [voices, setVoices] = useState<GlVoiceRow[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [playbookId, setPlaybookId] = useState("");
  const [port, setPort] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);
  const [note, setNote] = useState<string | null>(null);

  /**
   * `preserveRefusal` exists because of a real bug: after a refused start the panel
   * refreshes so the status panel reflects the blocked runtime — and a plain `load()`
   * clears the refusal on the way through, erasing the reason the start failed.
   */
  const load = useCallback(async (preserveRefusal = false) => {
    try {
      const [statusRes, pbRes, voiceRes] = await Promise.all([
        api.ghostlineStatus(),
        api.listGhostlinePlaybooks(),
        api.listGhostlineVoices(),
      ]);
      setStatus(statusRes);
      setPlaybooks(pbRes.playbooks.map((p) => toPlaybookRow(p)));
      setVoices(voiceRes.voices.map((w) => toVoiceRow(w as GlVoiceWire)));
      if (!preserveRefusal) setRefusal(null);
    } catch (err) {
      setRefusal(classify(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while running: a runtime can stop, or a tunnel can die, and a panel that
  // only refreshes on click would show a live-looking WSS URL that no longer answers.
  const running = status?.runtime.state === "running";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(id);
  }, [running, load]);

  const { providers, runtime } = useMemo(
    () =>
      status
        ? fromStatus(status)
        : { providers: [] as GlProviderRow[], runtime: null as GlRuntimeRow | null },
    [status],
  );

  const ready = runtime ? dialReadiness(runtime) : { ready: false, reason: "loading status" };

  const start = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    setNote(null);
    try {
      const res = await api.startGhostlineRuntime({
        voice_id: voiceId,
        playbook_id: playbookId,
        port: port ? Number(port) : null,
      });
      setNote(
        res.runtime.state === "running"
          ? `Runtime up on ${res.runtime.playbook_name ?? playbookId} · ${res.runtime.ws_url ?? "no media URL"}`
          : `Runtime ${res.runtime.state}.`,
      );
      await load();
    } catch (err) {
      setRefusal(classify(err));
      // A 424 carries the blocker list; after a failed start the status endpoint is
      // the better view of it, so refresh — but keep the refusal, which is the reason
      // the start failed and the first thing an operator needs to read.
      await load(true);
    } finally {
      setBusy(false);
    }
  }, [voiceId, playbookId, port, load]);

  const stop = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    try {
      await api.stopGhostlineRuntime();
      setNote("Runtime stopped and the tunnel was closed.");
      await load();
    } catch (err) {
      setRefusal(classify(err));
    } finally {
      setBusy(false);
    }
  }, [load]);

  const reload = useCallback(async () => {
    setBusy(true);
    try {
      const res = await api.reloadGhostlinePlaybooks();
      setNote(`Reloaded ${res.playbook_count} playbook(s) from the donor tree.`);
      await load();
    } catch (err) {
      setRefusal(classify(err));
    } finally {
      setBusy(false);
    }
  }, [load]);

  return (
    <GlShell
      title="GhostLine runtime"
      status={runtime ? <RuntimeDot runtime={runtime} testId="gl-runtime-dot" /> : null}
      testId="gl-runtime-panel"
    >
      <Refusal refusal={refusal} testId="gl-runtime-refusal" />

      {/* Provenance, not a second copy of the deck strip.
       *
       *  The deck above already states the donor, its licence, how many stage-engine
       *  modules run and how many live edges are up. Repeating those four numbers here
       *  made the panel read as a form with a summary glued to its top. What belongs on
       *  this panel and nowhere else is where the code came from and what each donor
       *  module is FOR — which is the part an auditor asks for and the part no readout
       *  carries. */}
      <div className="ui-ci-col">
        <span className="ui-pane-title">Provenance</span>
        <div className="ui-gl-provenance ui-holo ui-holo-edge" data-testid="gl-provenance">
          <div className="ui-gl-provenance-side">
            <strong data-testid="gl-donor-id">{status?.donor.donor_id ?? "—"}</strong>
            <span className="ui-id">
              {status
                ? `${status.donor.license} · ${status.donor.present ? "vendored" : "absent"}`
                : "loading"}
            </span>
            {status?.donor.repo ? (
              <a
                className="ui-gl-donor-repo"
                href={status.donor.repo}
                target="_blank"
                rel="noreferrer noopener"
                data-testid="gl-donor-repo"
              >
                {status.donor.repo}
              </a>
            ) : null}
            <code className="ui-id" title={status?.donor.root ?? ""}>
              {status?.donor.root ?? ""}
            </code>
          </div>
          <div className="ui-gl-provenance-side">
            <span className="op-label">what runs here</span>
            <span className="ui-id">
              the donor&apos;s stage engine — taxonomy, playbook schema, transition runner, mu-law
              codec, Twilio frame protocol — unmodified and imported from the vendor tree.
            </span>
          </div>
          <div className="ui-gl-provenance-side">
            <span className="op-label">what needs a key</span>
            <span className="ui-id">
              Twilio (PSTN), Deepgram (STT), ElevenLabs (TTS + cloning), a tunnel, and the
              persuasion model. Each needs a package and a credential; none is installed by default.
            </span>
          </div>
        </div>
        <Missing items={status?.missing ?? []} testId="gl-missing" />
      </div>

      {/* The composer: what `serve` takes. */}
      <div className="ui-ci-col">
        <span className="ui-pane-title">Composition</span>
        <div className="ui-gl-compose">
          <Select
            label="Voice"
            value={voiceId}
            onValueChange={setVoiceId}
            options={[
              { value: "", label: voices.length ? "choose a voice" : "no voices registered" },
              ...voices.map((v) => ({ value: v.voiceId, label: `${v.name} (${v.origin})` })),
            ]}
            data-testid="gl-voice-select"
          />
          <Select
            label="Playbook"
            value={playbookId}
            onValueChange={setPlaybookId}
            options={[
              { value: "", label: playbooks.length ? "choose a playbook" : "no playbooks loaded" },
              ...playbooks.map((p) => ({ value: p.playbookId, label: p.name })),
            ]}
            data-testid="gl-playbook-select"
          />
          <Input
            label="Port"
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="auto"
            hint="Only needed when the donor's own ngrok tunnel is used."
            data-testid="gl-port-input"
          />
        </div>
        <div className="ui-gl-actions">
          <Button
            variant="primary"
            size="sm"
            icon="activity"
            disabled={busy || !voiceId || !playbookId || runtime?.state === "running"}
            onClick={() => void start()}
            data-testid="gl-start"
          >
            Start runtime
          </Button>
          <Button
            size="sm"
            icon="close"
            disabled={busy || runtime?.state !== "running"}
            onClick={() => void stop()}
            data-testid="gl-stop"
          >
            Stop
          </Button>
          <Button
            size="sm"
            icon="refresh"
            disabled={busy}
            onClick={() => void reload()}
            data-testid="gl-reload-playbooks"
          >
            Reload playbooks
          </Button>
          <Button
            size="sm"
            icon="plus"
            disabled={busy}
            onClick={() => onNavigate?.("voices")}
            data-testid="gl-goto-voices"
          >
            Register a voice
          </Button>
        </div>
      </div>

      {/* Where calls go. */}
      <div className="ui-ci-col">
        <span className="ui-pane-title">Media endpoint</span>
        {runtime?.wsUrl ? (
          <div className="ui-ci-list" data-testid="gl-ws-url">
            <div className="ui-ci-list-row">
              <div className="ui-ci-list-main">
                <strong>WSS (Twilio dials back here)</strong>
                <code className="ui-id">{runtime.wsUrl}</code>
                <span className="ui-id">
                  {runtime.tunnelProvider ?? "unknown"} tunnel
                  {runtime.publicUrl ? ` · ${runtime.publicUrl}` : ""}
                  {runtime.mediaRouteServed ? " · media route served" : ""}
                </span>
              </div>
              <Chip label={runtime.playbookName ?? "no playbook"} tone="analytical" />
            </div>
          </div>
        ) : (
          <p className="panel-note" data-testid="gl-no-ws">
            {ready.reason}
          </p>
        )}
        {runtime?.model ? (
          <p className="ui-id" data-testid="gl-model">
            model {runtime.model} · modality {runtime.modality ?? "unknown"} · needs STT{" "}
            {String(runtime.needsDeepgram)} · needs TTS {String(runtime.needsElevenlabs)}
            {runtime.capabilitySource ? ` · capabilities from ${runtime.capabilitySource}` : ""}
          </p>
        ) : null}
      </div>

      {/* The setup checklist. */}
      <div className="ui-ci-col">
        <span className="ui-pane-title">Provider readiness</span>
        <ProviderList providers={providers} testId="gl-providers" />
      </div>

      {note ? (
        <p className="panel-note" data-testid="gl-runtime-note">
          {note}
        </p>
      ) : null}
    </GlShell>
  );
}
