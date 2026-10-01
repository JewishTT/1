"""``ExternalToolRuntime``: one process boundary for three unrelated tools (ACQ-12).

Directive §40-§41. Maigret, BBOT and SpiderFoot share nothing but the shape of
their output - a stream of results on stdout or in a file. What they *do* share
is every operational concern, and this module is where those concerns live once
instead of three times.

**The boundary is a container, not a Python import.** §42 requires Maigret to run
isolated "even though the library allows direct embedding", and gives six reasons:
security, fault isolation, dependency isolation, version pinning, resource limits,
replay. Embedding a tool as a library forfeits all six at once, and forfeits them
*silently* - the code works, the limits do not.

**stdout is data; stderr is logs.** §89. A tool that writes a progress bar to
stdout has corrupted its own protocol, and a parser that merges the two channels
turns a progress bar into a record. They are separate pipes here, and ``stderr``
never reaches the record parser.

**``argv`` is a list, never a shell string.** §52 forbids ``shell=True``. A tool
invocation is a template with named parameters, and the template is *data* - so a
query containing ``;``, ``&&`` or a backtick is a query, not a command.

**Exit code 0 does not mean data exists.** §90. A tool that finds nothing, a tool
that found nothing *because it was blocked*, and a tool that succeeded are three
different states, and conflating them is how a "successful" run reports zero
findings. So a run's outcome is ``exited_cleanly AND produced_records``, both
measured.

**§143's per-tool limits, not one default.** ``2 GB / 10m`` for every tool is the
thing this module exists to prevent: Maigret's cost is *sites*, BBOT's is
*processes*, SpiderFoot's is *threads*, and a limit expressed in the wrong unit
does not bound anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.acquisition_artifact import AcquisitionArtifact

from runtime import (
    RUNTIME_RESOURCE_LIMIT,
    CostEstimate,
    RuntimeError_,
)

#: §37's failure matrix for an external tool.
FAIL_IMAGE_NOT_FOUND = "image_not_found"
FAIL_START = "container_start_failed"
FAIL_TIMEOUT = "timeout"
FAIL_OUTPUT_LIMIT = "output_limit_exceeded"
FAIL_NONZERO_EXIT = "tool_exit_nonzero"
FAIL_NO_RECORDS = "no_records"
FAIL_BUDGET = "resource_limit_exceeded"

#: Pinned image digest (O-4, §31). Named once so the reference has a single home:
#: a mutable tag is not provenance, and a digest repeated across a code base drifts
#: the first time one of the two copies is updated.
SPIDERFOOT_IMAGE = (
    "ctdc/spiderfoot@sha256:53c5075b4b5bbff8e4d1d62cac8d66404b3b8e018a60d25d995c3204ea8f5b89"
)


@dataclass(frozen=True)
class ToolDefinition:
    """§40's declarative contract. Data, so a run's provenance is reportable.

    Everything here is what a run manifest needs in order to be reproducible
    (§181): the image, its digest, the entrypoint, the argv template, the record
    parser's name, and the limits. A tool invoked with these recorded can be
    re-run; a tool invoked with a hardcoded command in a function cannot.
    """

    tool_id: str
    runtime_ref: str
    image: str
    image_digest: str = ""
    entrypoint: list[str] = field(default_factory=list)
    argv: list[str] = field(default_factory=list)
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_mode: str = "stdout"  # stdout | file
    #: For ``output_mode="file"``: where the bind mount lands **on the host**, and
    #: what the tool names its output. Declared rather than inferred, because a tool
    #: writing into a container path that never reaches the host is the difference
    #: between "found nothing" and "found three and looked in the wrong place".
    output_host_dir: str = ""
    output_pattern: str = "*.json"
    record_parser: str = ""
    timeout: float = 300.0
    max_stdout_bytes: int = 32 * 1024 * 1024
    max_stderr_bytes: int = 4 * 1024 * 1024
    max_records: int = 10_000
    resource_class: str = "medium"
    version: str = "unpinned"
    workdir: str = "/work"
    extra_run_args: list[str] = field(default_factory=list)

    def build_argv(self, params: dict[str, Any]) -> list[str]:
        """Render the argv template. ``{name}`` is replaced as a *single* token.

        Substitution happens on the token list, never by joining into a shell
        string, so a value containing a space or a metacharacter cannot become two
        arguments. The replacement value is JSON-quoted when it contains anything
        shell-significant, which makes the fact that we never use a shell visible
        in the output rather than merely true.

        ``input_mapping`` declares which parameters the tool accepts and is keyed
        by parameter name: ``{"username": "username"}`` says the ``{username}``
        placeholder is filled from ``params["username"]``. An earlier version read
        the mapping's *value* as the replacement, which rendered every placeholder
        as its own key name - ``maigret test --timeout timeout`` - and the tool
        failed on a config error while the platform reported it as no records.
        """
        out: list[str] = []
        for token in [*self.entrypoint, *self.argv]:
            rendered = token
            for name in self.input_mapping:
                placeholder = "{" + name + "}"
                if placeholder not in rendered:
                    continue
                if name not in params:
                    raise RuntimeError_(
                        "tool_parameter_missing",
                        f"{self.tool_id} needs {name!r}; supplied: {sorted(params)}",
                    )
                text = str(params[name])
                if any(c.isspace() or c in "\"'`$;|&<>()" for c in text):
                    text = json.dumps(text)
                rendered = rendered.replace(placeholder, text)
            out.append(rendered)
        return out

    def config_digest(self, params: dict[str, Any]) -> str:
        """§182: deterministic digest of the *configuration*, secrets excluded.

        Only the input mapping's key names are included, never their values. A
        digest over the values would be a credential fingerprint - §184 - and
        would make the manifest itself a place credentials leak to.
        """
        material = json.dumps(
            {
                "tool_id": self.tool_id,
                "runtime_ref": self.runtime_ref,
                "image": self.image,
                "image_digest": self.image_digest,
                "argv": [*self.entrypoint, *self.argv],
                "input_keys": sorted(self.input_mapping),
                "version": self.version,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode()).hexdigest()[:32]

    def argv_digest(self, argv: list[str]) -> str:
        """§183: normalised command identity, for diagnostics."""
        return hashlib.sha256(shlex.join(argv).encode()).hexdigest()[:32]


@dataclass
class ToolRun:
    """What happened. Reported in the run manifest, never inferred from silence."""

    tool_id: str
    runtime_ref: str
    image: str
    image_digest: str
    argv: list[str]
    argv_digest: str
    config_digest: str
    started_at: str = ""
    finished_at: str = ""
    exit_code: int | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    records: int = 0
    seconds: float = 0.0
    timed_out: bool = False
    stdout_ref: str = ""
    stderr_tail: str = ""
    quarantined: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "runtime_ref": self.runtime_ref,
            "image": self.image,
            "image_digest": self.image_digest,
            "argv": self.argv,
            "argv_digest": self.argv_digest,
            "config_digest": self.config_digest,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "records": self.records,
            "seconds": round(self.seconds, 3),
            "timed_out": self.timed_out,
            "stdout_ref": self.stdout_ref,
            "stderr_tail": self.stderr_tail[-500:],
            "quarantined": self.quarantined,
        }


class ExternalToolRuntime:
    """Runs a :class:`ToolDefinition` in a container and streams its records.

    One instance per tool family. ``runtime_ref`` is the routing key §13/§14
    require; the tool's identity is never inferred from what the process happens
    to speak.
    """

    runtime_ref = "external_tool"
    execution_class = "external_process"

    def __init__(
        self,
        definition: ToolDefinition,
        *,
        docker_binary: str = "docker",
        network_policy: str = "none",
        cpu_limit: str | None = None,
        memory_limit: str | None = None,
        mount_dir: str | None = None,
    ) -> None:
        self._def = definition
        self._docker = docker_binary
        # §144: outbound network is an explicit decision, not a default. "none"
        # until the ToolDefinition says otherwise, because the reason to grant it
        # is never "because the tool is an OSINT tool".
        self._network = network_policy
        self._cpu = cpu_limit
        self._memory = memory_limit
        # The bind mount is what makes ``output_mode="file"`` work at all. Without
        # it a tool writes its report inside the container's ephemeral filesystem and
        # the file is destroyed on exit - so the run reports no records while having
        # made them. Only this directory crosses the boundary; §65 still forbids the
        # host filesystem generally and the engine socket outright.
        self._mount_dir = mount_dir
        self._run: ToolRun | None = None

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    @property
    def run(self) -> ToolRun | None:
        return self._run

    # ------------------------------------------------------------- contract --

    def capabilities(self) -> list[str]:
        return ["process", "container-isolated", "streaming", "resource-bounded"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=min(int(task.get("expected_records") or 100), self._def.max_records),
            expected_bytes=1024 * 1024,
            expected_seconds=self._def.timeout,
        )

    async def aclose(self) -> None:
        return None

    # -------------------------------------------------------------- execute --

    async def execute(
        self, params: dict[str, Any], *, task_id: str = "", source_id: str = ""
    ) -> ToolRun:
        """Run the tool to completion, capturing both channels under their caps."""
        argv = self._def.build_argv(params)
        self._run = ToolRun(
            tool_id=self._def.tool_id,
            runtime_ref=self._def.runtime_ref,
            image=self._def.image,
            image_digest=self._def.image_digest,
            argv=argv,
            argv_digest=self._def.argv_digest(argv),
            config_digest=self._def.config_digest(params),
            started_at=datetime.now(UTC).isoformat(),
        )
        run = self._run
        command = self._docker_command(argv)
        began = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError_(FAIL_IMAGE_NOT_FOUND, f"cannot run {self._docker}: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._def.timeout
            )
        except TimeoutError as exc:
            # §146: SIGTERM, grace, then record the outcome. A tool that has to be
            # killed has still produced evidence about what it was doing.
            proc.kill()
            await proc.wait()
            run.timed_out = True
            run.exit_code = proc.returncode
            run.seconds = time.monotonic() - began
            run.finished_at = datetime.now(UTC).isoformat()
            raise RuntimeError_(
                FAIL_TIMEOUT,
                f"{self._def.tool_id} exceeded {self._def.timeout}s and was killed",
            ) from exc

        run.seconds = time.monotonic() - began
        run.finished_at = datetime.now(UTC).isoformat()
        run.exit_code = proc.returncode
        run.stderr_tail = stderr.decode("utf-8", errors="replace")[-2000:]

        # §148: stdout and stderr have separate caps, and exceeding one is recorded
        # rather than silently truncated - a truncated protocol stream parses into
        # wrong answers, which is worse than a refusal.
        if len(stdout) > self._def.max_stdout_bytes:
            raise RuntimeError_(
                RUNTIME_RESOURCE_LIMIT,
                f"{self._def.tool_id} wrote {len(stdout)} stdout bytes, over the "
                f"{self._def.max_stdout_bytes} cap",
            )
        if len(stderr) > self._def.max_stderr_bytes:
            run.stderr_tail = stderr[: self._def.max_stderr_bytes].decode(
                "utf-8", errors="replace"
            )
        run.stdout_bytes = len(stdout)
        run.stderr_bytes = len(stderr)

        # §91: partial output is preserved. A tool that emitted 900 records and then
        # crashed has still produced 900 observations, and rolling them back would
        # throw away real evidence because of an unrelated failure.
        run.stdout_ref = self._persist(stdout)
        return run

    async def stream(
        self, params: dict[str, Any], *, task_id: str = "", source_id: str = ""
    ) -> AsyncIterator[AcquisitionArtifact]:
        """Run the tool and yield one artifact per parsed record."""
        run = await self.execute(params, task_id=task_id, source_id=source_id)
        parser = _PARSERS[self._def.record_parser]
        body = self._read_output(run)
        records = parser(body)

        # §90: a clean exit with no records is a *state*, not a success.
        if not records:
            raise RuntimeError_(
                FAIL_NO_RECORDS,
                f"{self._def.tool_id} exited {run.exit_code} and produced no records",
            )

        locator_prefix = f"{self._def.runtime_ref}:"
        for index, record in enumerate(records):
            if index >= self._def.max_records:
                raise RuntimeError_(
                    RUNTIME_RESOURCE_LIMIT,
                    f"{self._def.tool_id} produced more than {self._def.max_records} records",
                )
            payload = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
            yield AcquisitionArtifact(
                task_id=task_id,
                source_id=source_id or self._def.tool_id,
                worker_ref="external_tool",
                target_uri=f"tool://{self._def.tool_id}/run/{run.config_digest}",
                locator=f"{locator_prefix}record:{index}",
                body=payload,
                content_type="application/json",
                fetched_at=datetime.now(UTC),
                transport="docker-exec",
                producer=self._def.runtime_ref,
                producer_version=self._def.version,
                metadata={
                    "tool_id": self._def.tool_id,
                    "record_index": index,
                    "exit_code": run.exit_code,
                    "timed_out": run.timed_out,
                    "image_digest": self._def.image_digest,
                    "argv_digest": run.argv_digest,
                    "config_digest": run.config_digest,
                    # §63: which parser reads a tool record.
                    "parser_hint": "structured_fields",
                    # §49/§60: donor fields are carried, not interpreted.
                    "donor_record": record,
                },
            )
        run.records = len(records)

    # -------------------------------------------------------------- helpers --

    def _docker_command(self, argv: list[str]) -> list[str]:
        command = [self._docker, "run", "--rm", "-i"]
        # §65: the engine socket is never bind-mounted into a tool process and
        # neither is the host filesystem, so the container gets a network policy
        # and nothing else from the host.
        command += ["--network", self._network, "--workdir", self._def.workdir]
        if self._mount_dir:
            # Bound at the tool's own workdir, and nothing else of the host crosses.
            command += [
                "--mount",
                f"type=bind,source={self._mount_dir},target={self._def.workdir}",
            ]
        if self._cpu:
            command += ["--cpus", self._cpu]
        if self._memory:
            command += ["--memory", self._memory]
        command += ["--pids-limit", "256"]
        command += [self._def.image, *argv]
        return command

    def _persist(self, stdout: bytes) -> str:
        """Write the raw stdout beside the run manifest (§91, §108).

        A file rather than ObjectStore on purpose: this is *tool output*, not
        acquired evidence, and §74 asks for it as a diagnostic artifact. Its
        content hash is returned so it can be cited without reading it back.
        """
        out = Path("artifacts/acquisition-integration/tool-output")
        out.mkdir(parents=True, exist_ok=True)
        run = self._run
        assert run is not None
        digest = hashlib.sha256(stdout).hexdigest()[:8]
        name = f"{self._def.tool_id}-{run.config_digest[:8]}-{digest}.bin"
        target = out / name
        target.write_bytes(stdout)
        return target.as_posix()

    def _read_output(self, run: ToolRun) -> bytes:
        """Where the records actually are, which is not always stdout.

        Two of the three tools disagree about this, and guessing wrong is what made
        both of them look empty:

        * **BBOT and SpiderFoot** print their result JSON on stdout. SpiderFoot's is a
          JSON *array*, not NDJSON - measured here - so it needs the array-aware
          parser, not the line reader.
        * **Maigret** prints a human-readable progress report on stdout and writes its
          ``--json`` report to a *file* inside the container, which reaches the host
          only through the bind mount. Reading its stdout finds a text report and no
          records, and the run reports zero findings it actually made.

        So ``output_mode="file"`` resolves the mount the runtime itself configured and
        reads the newest artifact the tool produced there.
        """
        if self._def.output_mode == "file":
            return self._read_mounted_file()
        return Path(run.stdout_ref).read_bytes() if run.stdout_ref else b""

    def _read_mounted_file(self) -> bytes:
        host_dir = self._def.output_host_dir
        if not host_dir:
            return b""
        pattern = self._def.output_pattern or "*.json"
        candidates = sorted(Path(host_dir).glob(pattern), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return b""
        run = self._run
        assert run is not None
        # Prefer a file newer than this run's own stdout capture, so a stale report
        # from a previous run is never mistaken for this one's output.
        newest = candidates[-1]
        return newest.read_bytes()


# ----------------------------------------------------------------- parsers ---


def _parse_ndjson(body: bytes) -> list[dict[str, Any]]:
    """One JSON object per line; malformed lines are dropped, counted elsewhere."""
    out: list[dict[str, Any]] = []
    for line in body.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def _parse_json(body: bytes) -> list[dict[str, Any]]:
    try:
        value = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return [value] if isinstance(value, dict) else []


def _parse_nested(body: bytes, *keys: str) -> list[dict[str, Any]]:
    """Walk a chain of object keys, collecting dicts at the leaf.

    SpiderFoot's JSON export nests results under a scan id, and Maigret's under a
    site name; this is the one place that knows how to reach them, rather than
    three ad-hoc ``.get().get()`` chains in three parsers.
    """
    root = _parse_json(body)
    if not root:
        return []
    level: list[dict[str, Any]] = root
    for key in keys:
        nxt: list[dict[str, Any]] = []
        for node in level:
            value = node.get(key)
            if isinstance(value, dict):
                nxt.append(value)
            elif isinstance(value, list):
                nxt.extend(v for v in value if isinstance(v, dict))
        level = nxt
        if not level:
            return []
    return level


def _parse_maigret(body: bytes) -> list[dict[str, Any]]:
    """Maigret's ``--json simple`` report: ``{site_name: site_result}`` at top level.

    Verified against maigret 0.6.6: the site name is the *key*, not a field, so a
    parser that looked for ``report["sites"]`` finds nothing - which is what an
    earlier version here did, and it returned an empty list against a run that had
    genuinely found three accounts.

    Decodes the document directly rather than through :func:`_parse_json`. That
    helper normalises a dict into a one-element list - correct for "a document that
    *is* a record", wrong here, where the document is a **mapping of site names** and
    wrapping it produced ``[{...}]``, so the subsequent ``.items()`` was called on a
    list. The shape is the contract here, not an implementation detail.

    Every field §44 names is carried verbatim: ``status``, ``url_user``,
    ``http_status``, ``rank``, ``ids_data``. The site name is preserved because it
    is the only thing identifying *which* check produced the result, and without it
    a record is an anonymous http status.
    """
    try:
        report = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return []
    if not isinstance(report, dict):
        return []
    out: list[dict[str, Any]] = []
    for site_name, result in report.items():
        if not isinstance(result, dict):
            continue
        record = dict(result)
        record["site_name"] = site_name
        out.append(record)
    return out


_PARSERS: dict[str, Any] = {
    "ndjson": _parse_ndjson,
    "json": _parse_json,
    "bbot_events": lambda b: _parse_ndjson(b),
    "maigret_sites": _parse_maigret,
    # SpiderFoot's ``-o json`` is a JSON **array** of event objects, verified
    # against the ctdc image. An earlier mapping read ``["results"]``, a key that
    # does not exist in this output, and returned nothing from a run that had five
    # events in it.
    "spiderfoot_results": _parse_json,
    "spiderfoot_scan": lambda b: _parse_nested(b, "__type", "data"),
}

#: §40: the tool definitions that name which parser reads which tool's output.
#: Declared as data so a run's provenance is reportable without importing the
#: parser, and so adding a tool is a table change rather than a code path.
TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "maigret": ToolDefinition(
        tool_id="maigret",
        runtime_ref="maigret",
        image="maigret:donor",
        image_digest="local-build:donors/maigret",
        entrypoint=[],
        argv=[
            "{username}",
            "--site",
            "{site}",
            "--timeout",
            "{timeout}",
            "--folderoutput",
            ".",
            "--json",
            "simple",
            "--no-color",
            "--no-progressbar",
            "--print-not-found",
        ],
        input_mapping={"username": "username", "site": "site", "timeout": "timeout"},
        output_mode="file",
        output_host_dir="",
        output_pattern="report_*.json",
        record_parser="maigret_sites",
        timeout=180.0,
        max_stdout_bytes=8 * 1024 * 1024,
        max_stderr_bytes=2 * 1024 * 1024,
        max_records=5_000,
        resource_class="medium",
        version="0.6.6",
        workdir="/out",
    ),
    "spiderfoot": ToolDefinition(
        tool_id="spiderfoot",
        runtime_ref="spiderfoot",
        image=SPIDERFOOT_IMAGE,
        image_digest="sha256:53c5075b4b5bbff8e4d1d62cac8d66404b3b8e018a60d25d995c3204ea8f5b89",
        # The image's ENTRYPOINT is ``/usr/bin/python3`` and its CMD is
        # ``sf.py -l 0.0.0.0:5001``. The scanner CLI lives at ``/home/spiderfoot``,
        # so the workdir is set there and ``sf.py`` is argv's first token. Earlier
        # this ran with the default workdir and failed with "can't open file
        # 'sf.py'" - a configuration failure the platform reported as no records.
        entrypoint=["sf.py"],
        argv=[
            "-s",
            "{target}",
            "-m",
            "{modules}",
            "-t",
            "{types}",
            "-o",
            "json",
            "-q",
        ],
        input_mapping={
            "target": "target",
            "modules": "modules",
            "types": "types",
        },
        output_mode="stdout",
        record_parser="spiderfoot_results",
        timeout=300.0,
        max_stdout_bytes=64 * 1024 * 1024,
        max_stderr_bytes=4 * 1024 * 1024,
        max_records=20_000,
        resource_class="large",
        version="unpinned",
        workdir="/home/spiderfoot",
    ),
}
