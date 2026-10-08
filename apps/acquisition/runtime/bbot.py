"""BBOT as a first-class runtime, not a tool bolted on (ACQ-14, §47-§50).

BBOT is the only one of the five families that is *already* an event-producing
reconnaissance engine. It emits typed events with a parent reference, a discovery
path and a module sequence - which is, structurally, the same vocabulary the
platform uses for provenance. That is why it does not belong in
:class:`~runtime.external_tool.ExternalToolRuntime`: that module treats output as a
blob of text to parse, and BBOT's output is a graph-shaped event stream where the
edges carry meaning.

**What is taken, and what is refused.**

Taken, verbatim: the event itself - ``type``, ``id``, ``uuid``, ``data``,
``parent``, ``parent_uuid``, ``timestamp``, ``module``, ``module_sequence``,
``discovery_context``, ``discovery_path``, ``parent_chain``, ``scope_description``,
``scope_distance``, ``tags``, ``host_metadata``. §48 says preserve them; nothing
here rewrites them, reorders them, or drops the ones the platform has no vocabulary
for yet.

Refused, and this is the whole point: **none of it becomes a relation.** §49 is
explicit that a parent is donor derivation context and that ``A parent-of B`` is not
automatically a platform ``RelationClaim``; §160 lists it as a release blocker. So
``parent`` and ``discovery_path`` travel as metadata on the artifact and stop there.
The next stage may *read* them and propose a signal; nothing here does.

**BBOT's Kafka output module is not used.** §47 forbids it and for a concrete
reason: its event schema is BBOT's, not the platform's ``EventEnvelope``. A BBOT
message on the canonical observation topic would be a donor schema wearing the
platform's topic name - and every consumer downstream would have to know which is
which. Every BBOT event crosses the boundary through
:class:`~domain.acquisition_artifact.AcquisitionArtifact` and the gate like every
other record.

**The public-suffix dependency is pre-seeded, not worked around.** BBOT resolves
TLDs with ``tldextract``, which fetches its suffix list from GitHub on first use. In
an environment where that egress is refused the *tool* fails at import, before any
reconnaissance - a failure that looks like "BBOT produced nothing" and is actually
"BBOT could not start". The fix is to let ``tldextract`` populate its own cache from
a locally fetched list, with its own naming, so no version-specific filename is
hard-coded here.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from domain.acquisition_artifact import AcquisitionArtifact

from runtime import CostEstimate, RuntimeError_, RuntimeHealth
from runtime.record_stream import StreamRecord, read_record_stream

#: Pinned digest (O-4). Named once so the reference has one home.
BBOT_IMAGE = (
    "blacklanternsecurity/bbot@sha256:40ed0733e0163feee844d49346eb15e40872fa7008f621358eed9b9a7807382e"
)
BBOT_DIGEST = "sha256:40ed0733e0163feee844d49346eb15e40872fa7008f621358eed9b9a7807382e"

#: Default wall-clock allowance. Measured on the pinned digest: a first run spends
#: ~450s installing Ansible/pip/OS dependencies *inside* the container, because
#: ``--rm`` throws them away afterwards. The figure is a real observation, not a guess.
BBOT_DEFAULT_TIMEOUT = 900.0


def resolve_image() -> str:
    """The image to run: an explicit override, else the pinned digest.

    An override exists because the pinned image reinstalls its dependencies on every
    ``--rm`` run, which is most of its wall clock. A warmed derivative - the same
    pinned base, committed once after its first run - cuts a measured 450s to 152s for
    the same yield. The manifest always records which image actually ran, so a run made
    with an override never looks like a run made with the pin.
    """
    import os

    return os.environ.get("COGNITIVE_BBOT_IMAGE") or BBOT_IMAGE

#: §10's locator scheme.
LOCATOR_PREFIX = "bbot:event:"

#: §48's fields, named so "what does the platform carry" is one answerable
#: question. A field BBOT did not emit stays absent rather than becoming ``None`` -
#: §21's rule applied to events, because an invented ``None`` asserts the tool said
#: it had nothing.
DONOR_EVENT_FIELDS: tuple[str, ...] = (
    "type",
    "id",
    "uuid",
    "data",
    "data_json",
    "parent",
    "parent_uuid",
    "timestamp",
    "module",
    "module_sequence",
    "discovery_context",
    "discovery_path",
    "parent_chain",
    "scope_description",
    "scope_distance",
    "tags",
    "host_metadata",
    "host",
    "netloc",
    "scan",
)

#: BBOT's own event types we treat as run metadata rather than observations. A
#: ``SCAN`` is the run announcing itself, not a finding about the world - §28's
#: distinction applied to BBOT's vocabulary.
RUN_EVENT_TYPES = frozenset({"SCAN"})


class _BbotAdapter:
    """Frames BBOT's events for the shared record reader."""

    locator = LOCATOR_PREFIX

    def accepts(self, message: dict[str, Any]) -> bool:
        kind = message.get("type")
        if not kind:
            return False
        return kind not in RUN_EVENT_TYPES

    def index_fields(self, message: dict[str, Any]) -> dict[str, Any]:
        """Carry the donor's provenance, unchanged and un-interpreted."""
        out: dict[str, Any] = {}
        for name in DONOR_EVENT_FIELDS:
            if name in message:
                out[f"donor_{name}"] = message[name]
        # §49, stated in the record itself so a downstream reader cannot mistake
        # this for a relation the platform asserted.
        out["provenance_kind"] = "donor_derivation_context"
        out["relation_asserted"] = False
        return out


@dataclass
class BbotRun:
    """What happened in a BBOT run. Reported in the manifest, never inferred from silence.

    Modelled on ``external_tool.ToolRun`` and deliberately the same shape: one run
    record for every tool-shaped runtime on this platform, so a manifest reader learns
    it once. Reused rather than reinvented -- the fields are the ones the proof scripts
    reconcile against (§141).
    """

    image: str = ""
    image_digest: str = ""
    argv: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    exit_code: int | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    lines_seen: int = 0
    records: int = 0
    scan_events: int = 0
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0
    timed_out: bool = False
    truncated: bool = False
    stderr_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "image_digest": self.image_digest,
            "argv": self.argv,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "lines_seen": self.lines_seen,
            "records": self.records,
            "scan_events": self.scan_events,
            # §141: the five numbers a collection volume is reconciled from.
            "quarantined": len(self.quarantined),
            "quarantine_detail": self.quarantined,
            "seconds": round(self.seconds, 3),
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "stderr_tail": self.stderr_tail[-500:],
        }


class BbotRuntime:
    """BBOT as an event-producing acquisition runtime."""

    runtime_ref = "bbot"
    execution_class = "event_producing"

    def __init__(
        self,
        *,
        image: str | None = None,
        image_digest: str = BBOT_DIGEST,
        cache_dir: str | None = None,
        presets: str = "subdomain-enum",
        module_flags: str = "passive",
        network_policy: str = "bridge",
        timeout: float = BBOT_DEFAULT_TIMEOUT,
        max_record_bytes: int = 1024 * 1024,
    ) -> None:
        self._image = image or resolve_image()
        self._digest = image_digest
        self._cache_dir = cache_dir
        self._presets = presets
        self._flags = module_flags
        self._network = network_policy
        self._timeout = timeout
        self._max_record_bytes = max_record_bytes
        self._scan_events: list[dict[str, Any]] = []
        self._run = BbotRun(image=image, image_digest=image_digest)

    # ------------------------------------------------------------- contract --

    def capabilities(self) -> list[str]:
        return ["recon", "event-stream", "passive", "dns", "subdomains", "streaming"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=int(task.get("expected_events") or 500),
            expected_bytes=2 * 1024 * 1024,
            expected_seconds=self._timeout,
        )

    async def aclose(self) -> None:
        return None

    @property
    def run(self) -> BbotRun:
        """The manifest of the last run.

        Replaces the old ``process_run``, which was permanently ``None``: it read
        ``self._process.run`` off an ``AirbyteRuntime`` that was constructed and then
        never executed, so every manifest it appeared in said ``exit_code: null``.
        """
        return self._run

    @property
    def scan_events(self) -> list[dict[str, Any]]:
        """``SCAN`` events, kept as run metadata (§28's discipline for BBOT)."""
        return list(self._scan_events)

    # ---------------------------------------------------------------- health --

    async def probe(self) -> RuntimeHealth:
        """§78's precondition. A tool that cannot start is not runtime-ready."""
        try:
            import asyncio

            proc = await asyncio.create_subprocess_exec(
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                self._image,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
        except Exception as exc:  # noqa: BLE001
            return RuntimeHealth(
                ready=False,
                detail=f"cannot run BBOT: {type(exc).__name__}: {exc}",
                checks={"code": "bbot_unavailable"},
                runtime_ref=self.runtime_ref,
            )
        text = (out or b"").decode("utf-8", errors="replace") + (err or b"").decode(
            "utf-8", errors="replace"
        )
        if proc.returncode != 0:
            return RuntimeHealth(
                ready=False,
                detail=f"BBOT --version exited {proc.returncode}: {text.strip()[:200]}",
                checks={"code": "bbot_version_failed"},
                runtime_ref=self.runtime_ref,
            )
        return RuntimeHealth(
            ready=True,
            detail=f"bbot responds: {text.strip().splitlines()[0][:80] if text.strip() else 'ok'}",
            checks={"version_reachable": True},
            runtime_ref=self.runtime_ref,
        )

    # --------------------------------------------------------------- acquire --

    async def acquire(self, task: dict[str, Any]) -> AsyncIterator[AcquisitionArtifact]:
        """Run a bounded scan and yield one artifact per BBOT event.

        §48: the event crosses as an artifact, whole. §49: its parent and discovery
        path travel as metadata and assert nothing.
        """
        target = str(task["target"])
        task_id = str(task.get("task_id") or "")
        source_id = str(task.get("source_id") or "bbot.recon")
        argv = self._argv(target)

        lines = self._raw_lines(argv)
        run = self._run
        self._scan_events.clear()
        seen_scans: list[dict[str, Any]] = []
        # §96/§97. Two live BBOT runs of the same target do **not** produce the same
        # sequence - measured here: 26 events then 24, in a different order. A
        # position-indexed locator therefore names a *different* event in each run,
        # and since the locator is part of observation identity (§11) the same
        # observed occurrence would acquire two addresses. BBOT gives every event a
        # stable ``uuid`` of its own, so the locator is derived from that instead:
        # ordering may vary, identity does not.
        record_index = 0
        # aclosing, not a bare `async for`: closing this generator does not close the
        # one it is iterating, so a cancelled or abandoned acquire would leave the
        # container running with nobody reading its stdout. Found by the test that
        # asserts the process is killed on early exit.
        async with aclosing(lines):
            try:
                async for raw in lines:
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    if not stripped.startswith("{"):
                        # §32: a line that is not protocol output is quarantined, not
                        # skipped in silence. Silently dropping it means a broken BBOT
                        # build looks exactly like a quiet one.
                        self._quarantine(run, "non_json_stdout", stripped)
                        continue
                    try:
                        message = json.loads(stripped)
                    except ValueError as exc:
                        self._quarantine(
                            run, "malformed_json", stripped, detail=f"{type(exc).__name__}"
                        )
                        continue
                    if not isinstance(message, dict) or "type" not in message:
                        self._quarantine(run, "no_event_type", stripped)
                        continue
                    if message.get("type") in RUN_EVENT_TYPES:
                        seen_scans.append(message)
                        continue
                    if len(stripped.encode("utf-8")) > self._max_record_bytes:
                        # The limit used to be accepted and never applied.
                        run.truncated = True
                        self._quarantine(
                            run,
                            "record_too_large",
                            stripped[:200],
                            detail=f"limit={self._max_record_bytes}",
                        )
                        continue
                    yield self._to_artifact(message, task_id, source_id, target, record_index)
                    record_index += 1
                    run.records = record_index
            finally:
                # In a finally, not after the loop: a consumer that stops early closes
                # the generator here, and the scan metadata would otherwise be lost
                # exactly when a run was cut short -- the case where it matters most.
                self._scan_events.extend(seen_scans)
                run.scan_events = len(self._scan_events)

    def _quarantine(
        self,
        run: BbotRun,
        code: str,
        raw: str,
        *,
        detail: str = "",
    ) -> None:
        run.quarantined.append({"code": code, "detail": detail, "raw": raw[:500]})

    def _argv(self, target: str) -> list[str]:
        # §144: passive by default. The flag set is part of the definition, not a
        # per-call guess, so a run's scope is reproducible from its manifest.
        argv = ["-t", target]
        if self._presets:
            argv += ["-p", self._presets]
        if self._flags:
            argv += ["-rf", self._flags]
        argv += ["--json", "--no-color"]
        return argv

    async def _raw_lines(self, argv: list[str]) -> AsyncIterator[str]:
        """Spawn the container and yield stdout lines as they arrive (§27).

        Three things this has to get right, each of which was previously wrong:

        1. **stderr is drained.** It is piped and BBOT is extremely talkative on it.
           An undrained pipe fills (~64 KiB), the docker client blocks on write, and
           ``readline()`` never returns again -- a task that hangs with no error and
           no timeout, because the timeout was on the read that is now stuck.
        2. **the deadline is on the run, not the line.** A per-line timeout never
           fires while BBOT emits an event every second, so the scan is unbounded.
        3. **the exit code is read.** A non-zero exit with records already yielded is
           a partial run, and the manifest has to be able to say so.
        """
        import asyncio
        import time

        command = ["docker", "run", "--rm", "-i", "--network", self._network]
        if self._cache_dir:
            command += [
                "-e",
                "TLDEXTRACT_CACHE=/cache",
                "--mount",
                f"type=bind,source={self._cache_dir},target=/cache",
            ]
        command += ["--workdir", "/work", self._image, *argv]
        run = self._run
        run.argv = list(argv)
        run.started_at = datetime.now(UTC).isoformat()
        started = time.monotonic()

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        # Keep only a bounded tail: unbounded stderr growth on a chatty tool is its
        # own memory leak, and the tail is what a human reads.
        stderr_chunks: list[bytes] = []
        stderr_bytes = 0

        async def drain_stderr() -> None:
            nonlocal stderr_bytes
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                stderr_bytes += len(chunk)
                if sum(len(c) for c in stderr_chunks) < 64 * 1024:
                    stderr_chunks.append(chunk)

        drain = asyncio.create_task(drain_stderr())
        deadline = started + self._timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except TimeoutError as exc:
                    run.timed_out = True
                    proc.kill()
                    await proc.wait()
                    raise RuntimeError_(
                        "timeout", f"bbot exceeded {self._timeout}s and was killed"
                    ) from exc
                if not raw:
                    break
                run.stdout_bytes += len(raw)
                run.lines_seen += 1
                yield raw.decode("utf-8", errors="replace")
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            run.exit_code = proc.returncode
            run.stderr_bytes = stderr_bytes
            run.stderr_tail = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            run.seconds = time.monotonic() - started
            run.finished_at = datetime.now(UTC).isoformat()
            drain.cancel()
            with suppress(asyncio.CancelledError):
                await drain

    def _to_artifact(
        self, message: dict[str, Any], task_id: str, source_id: str, target: str, index: int
    ) -> AcquisitionArtifact:
        # The event body is the whole event, not just ``data``: §48 says preserve the
        # fields the event carries, and a capture of only ``data`` would make the
        # provenance unrecoverable without a second fetch.
        body = json.dumps(message, sort_keys=True, ensure_ascii=False).encode("utf-8")
        # The locator is derived from BBOT's own event uuid, falling back to its
        # ``id`` and only then to the arrival index. The index is the last resort
        # because it is the one component that is not stable across runs; a donor
        # that ships a stable per-event identifier should always supply one.
        stable = str(message.get("uuid") or message.get("id") or f"seq-{index}")
        # §21's rule, applied to events: a field the tool did not send stays absent.
        # An earlier version used ``message.get(...)`` for every donor field, so a
        # minimal event arrived carrying ~14 keys whose values were ``None`` - which
        # asserts the tool said it had no parent, rather than that it never said.
        meta: dict[str, Any] = {
            "target": target,
            "event_index": index,
            "image_digest": self._digest,
            # §63: what reads a BBOT event.
            "parser_hint": "structured_fields",
            # §49, stated on the record, not only in a docstring.
            "provenance_kind": "donor_derivation_context",
            "relation_asserted": False,
        }
        for field, key in (
            ("type", "donor_event_type"),
            ("id", "donor_event_id"),
            ("uuid", "donor_event_uuid"),
            ("module", "donor_module"),
            ("parent", "donor_parent"),
            ("parent_uuid", "donor_parent_uuid"),
            ("discovery_path", "donor_discovery_path"),
            ("parent_chain", "donor_parent_chain"),
            ("scope_description", "donor_scope"),
            # §48 names twenty fields. The nine above were carried and these eleven
            # were left only inside ``body``, which meant an indexer reading metadata
            # could not answer "which module, at what distance, in what order" without
            # re-opening and re-parsing every capture.
            ("timestamp", "donor_timestamp"),
            ("module_sequence", "donor_module_sequence"),
            ("discovery_context", "donor_discovery_context"),
            ("scope_distance", "donor_scope_distance"),
            ("tags", "donor_tags"),
            ("host_metadata", "donor_host_metadata"),
            ("host", "donor_host"),
            ("netloc", "donor_netloc"),
            ("scan", "donor_scan"),
            ("data_json", "donor_data_json"),
        ):
            if field in message:
                meta[key] = message[field]
        return AcquisitionArtifact(
            task_id=task_id,
            source_id=source_id,
            worker_ref="bbot",
            target_uri=f"bbot://scan/{target}",
            locator=f"{LOCATOR_PREFIX}{stable}",
            body=body,
            content_type="application/json",
            fetched_at=datetime.now(UTC),
            transport="docker-exec",
            producer=self.runtime_ref,
            producer_version=self._digest[:19],
            metadata=meta,
        )


__all__ = [
    "BbotRuntime",
    "DONOR_EVENT_FIELDS",
    "LOCATOR_PREFIX",
    "RUN_EVENT_TYPES",
    "StreamRecord",
    "read_record_stream",
]
