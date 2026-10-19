import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import { Chip, Empty, GlShell, Missing, Refusal } from "../panelParts";
import { toVoiceRow } from "../model";
import type { GlRefusal, GlVoiceRow } from "../types";

/**
 * Voices panel (Feature 031) — the donor's `clone` verb.
 *
 * The CLI's version is one command that prints an id for you to copy: `ghostline clone
 * sample.wav --name helpdesk`. That is a bad fit for a browser in two ways, and this
 * panel fixes both:
 *
 * * **A premade voice is a first-class thing.** GhostLine's own documentation tells
 *   operators on ElevenLabs' free tier that instant cloning is unavailable and that they
 *   should pick a stock voice id from the provider's console. That id is a perfectly good
 *   voice and the CLI has nowhere to record it. So registering one is the primary path
 *   here, and origin is kept as a visible distinction — cloned and premade are not the
 *   same thing to an operator.
 * * **A clone is a file, and a file arrives from outside.** The upload is size-capped,
 *   its format is checked against what the donor's reader actually handles (WAV, M4A via
 *   ffmpeg), and its stored name is derived server-side rather than taken from the
 *   browser — because a client-supplied filename decides where a write lands.
 *
 * `origin` matters for more than bookkeeping: a clone is a reproduction of a real
 * person's voice, and an assessment record that does not distinguish one from a stock
 * voice is not a record an assessor can sign.
 */
export function VoicesPanel() {
  const [voices, setVoices] = useState<GlVoiceRow[] | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // Premade registration
  const [voiceId, setVoiceId] = useState("");
  const [voiceName, setVoiceName] = useState("");

  // Clone
  const [cloneName, setCloneName] = useState("");
  const [sampleRef, setSampleRef] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listGhostlineVoices();
      setVoices(res.voices.map((v) => toVoiceRow(v)));
      setMissing(res.missing ?? []);
      setRefusal(null);
    } catch (err) {
      setRefusal(classify(err));
      setVoices([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const register = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    setNote(null);
    try {
      const res = await api.registerGhostlineVoice({
        voice_id: voiceId,
        name: voiceName || voiceId,
        origin: "premade",
      });
      setNote(`Registered ${res.voice.name} (${res.voice.voice_id}).`);
      setVoiceId("");
      setVoiceName("");
      await load();
    } catch (err) {
      setRefusal(classify(err));
    } finally {
      setBusy(false);
    }
  }, [voiceId, voiceName, load]);

  const clone = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    setNote(null);
    try {
      if (file) {
        // base64 without the data-url prefix: the server decodes the payload itself.
        const base64 = await readAsBase64(file);
        const res = await api.cloneGhostlineVoice({
          name: cloneName,
          sample_base64: base64,
          sample_filename: file.name,
        });
        setNote(`Cloned ${res.voice.name} → ${res.voice.voice_id}.`);
      } else {
        const res = await api.cloneGhostlineVoice({ name: cloneName, sample_ref: sampleRef });
        setNote(`Cloned ${res.voice.name} → ${res.voice.voice_id}.`);
      }
      setCloneName("");
      setSampleRef("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (err) {
      setRefusal(classify(err));
    } finally {
      setBusy(false);
    }
  }, [cloneName, sampleRef, file, load]);

  const forget = useCallback(
    async (id: string) => {
      setBusy(true);
      setRefusal(null);
      try {
        await api.forgetGhostlineVoice(id);
        setNote(`Forgot ${id}.`);
        await load();
      } catch (err) {
        setRefusal(classify(err));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  return (
    <GlShell
      title="Voice registry"
      status={
        voices ? (
          <Chip
            label={`${voices.length} registered`}
            tone={voices.length > 0 ? "accent" : "gold"}
            testId="gl-voice-count"
          />
        ) : null
      }
      testId="gl-voices-panel"
    >
      <Refusal refusal={refusal} testId="gl-voices-refusal" />

      <div className="ui-gl-split">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Register a premade voice</span>
          <p className="panel-note">
            Cloning needs a paid ElevenLabs plan. On the free tier, pick a stock voice from the
            provider&apos;s console and record its id here — the runtime speaks it exactly as it
            would speak a clone.
          </p>
          <Input
            label="Voice id"
            value={voiceId}
            onChange={(e) => setVoiceId(e.target.value)}
            placeholder="21m00Tcm4TlvDq8ikWAM"
            mono
            data-testid="gl-premade-id"
          />
          <Input
            label="Display name"
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            placeholder="support desk"
            data-testid="gl-premade-name"
          />
          <div>
            <Button
              size="sm"
              icon="plus"
              disabled={busy || voiceId.trim().length === 0}
              onClick={() => void register()}
              data-testid="gl-register-voice"
            >
              Register
            </Button>
          </div>
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Clone a voice</span>
          <Input
            label="Clone name"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            placeholder="helpdesk"
            data-testid="gl-clone-name"
          />
          <Input
            label="Sample already on disk (optional)"
            value={sampleRef}
            onChange={(e) => setSampleRef(e.target.value)}
            placeholder="sample.wav"
            mono
            hint="A name under the configured samples root, not a path."
            disabled={file !== null}
            data-testid="gl-clone-ref"
          />
          <span className="ui-field">
            <label className="ui-field-label" htmlFor="gl-clone-file">
              Sample upload (optional)$r
            </label>
            <input
              id="gl-clone-file"
              ref={fileInput}
              type="file"
              accept=".wav,.m4a,audio/wav,audio/mp4"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              data-testid="gl-clone-file"
            />
            <span className="ui-field-hint">
              WAV or M4A, 25 MB cap. Uploading clears the field above.
            </span>
          </span>
          <div>
            <Button
              size="sm"
              icon="activity"
              disabled={
                busy || cloneName.trim().length === 0 || (sampleRef.trim().length === 0 && !file)
              }
              onClick={() => void clone()}
              data-testid="gl-clone-voice"
            >
              Clone from sample
            </Button>
          </div>
          <Missing items={missing} testId="gl-clone-missing" />
        </div>
      </div>

      <div className="ui-ci-col">
        <span className="ui-pane-title">Registered</span>
        {voices === null ? (
          <Empty>Loading…</Empty>
        ) : voices.length === 0 ? (
          <Empty>No voices yet. A runtime needs one before it can be started.</Empty>
        ) : (
          <ul className="ui-ci-list" data-testid="gl-voice-list">
            {voices.map((voice) => (
              <li key={voice.voiceId} className="ui-ci-list-row">
                <div className="ui-ci-list-main">
                  <strong>{voice.name}</strong>
                  <code className="ui-id">{voice.voiceId}</code>
                  <span className="ui-id">
                    {voice.sampleRef ? `sample ${voice.sampleRef}` : "no sample"}
                    {voice.sampleBytes != null
                      ? ` · ${Math.round(voice.sampleBytes / 1024)} KB`
                      : ""}
                    {voice.notes ? ` · ${voice.notes}` : ""}
                  </span>
                </div>
                <Chip
                  label={voice.origin}
                  tone={voice.origin === "cloned" ? "analytical" : "neutral"}
                  title={
                    voice.origin === "cloned"
                      ? "A reproduction of a specific person's voice."
                      : "A stock voice from the provider's library."
                  }
                  testId={`gl-voice-origin-${voice.voiceId}`}
                />
                <Button
                  size="sm"
                  icon="close"
                  disabled={busy}
                  onClick={() => void forget(voice.voiceId)}
                  data-testid={`gl-forget-${voice.voiceId}`}
                >
                  Forget
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {note ? (
        <p className="panel-note" data-testid="gl-voices-note">
          {note}
        </p>
      ) : null}
    </GlShell>
  );
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`could not read ${file.name}`));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

function classify(err: unknown): GlRefusal {
  const apiErr = err as { status?: number; message?: string; detail?: unknown };
  const detail = apiErr.detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    const code = String((detail as { error: unknown }).error);
    if (code === "VoiceUnavailable") {
      const reason = String((detail as { reason?: unknown }).reason ?? apiErr.message ?? "");
      // 422 from the clone route is a named, fixable reason (bad format, too big,
      // missing provider) rather than an authorisation verdict.
      return { kind: "setup", reason };
    }
    if (apiErr.status === 409) {
      return {
        kind: "gate",
        code,
        reason: String((detail as { reason?: unknown }).reason ?? ""),
        rejected: [],
      };
    }
    return {
      kind: "setup",
      reason: String((detail as { reason?: unknown }).reason ?? apiErr.message ?? ""),
    };
  }
  return { kind: "setup", reason: err instanceof Error ? err.message : String(err) };
}
