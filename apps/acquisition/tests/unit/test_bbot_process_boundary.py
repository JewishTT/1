"""Process-boundary tests for ``BbotRuntime``.

These exist because the boundary had **no** tests at all, and that is how a piped-but-
unread ``stderr`` shipped: on a talky tool the pipe fills, the docker client blocks on
write, and ``readline()`` stops returning. No unit test that never spawns a process can
see that, so the process is faked here rather than skipped.

The subprocess is a fake, not a mock: it is a real object with the same async
interface, driven by a script of "lines this process will produce", so ordering,
deadline and kill behaviour are exercised for real.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "apps" / "shared"))

from runtime.bbot import BbotRun, BbotRuntime  # noqa: E402


class FakeStream:
    """An asyncio stream backed by a list of chunks."""

    def __init__(self, chunks: list[bytes], *, hang_after: bool = False,
                 on_eof=None) -> None:
        self._chunks = list(chunks)
        self._hang_after = hang_after
        self._done = False
        self._on_eof = on_eof

    async def readline(self) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._hang_after:
            # Never returns. This is what a filled stderr pipe looks like from the
            # reader's side, and why an undrained pipe is a hang rather than a slow run.
            await asyncio.sleep(3600)
        if not self._done:
            self._done = True
            # stdout EOF means the process is exiting, exactly as it would in reality.
            # Without this the cleanup path cannot tell "exited" from "still running",
            # and would report a kill after every clean run.
            if self._on_eof:
                self._on_eof()
        return b""

    async def read(self, size: int = 4096) -> bytes:
        await asyncio.sleep(0)
        if self._chunks:
            chunk = self._chunks.pop(0)
            if len(chunk) > size:
                self._chunks.insert(0, chunk[size:])
                return chunk[:size]
            return chunk
        self._done = True
        return b""

    @property
    def at_eof(self) -> bool:
        return self._done and not self._chunks


class FakeProcess:
    def __init__(
        self,
        stdout_chunks: list[bytes],
        *,
        stderr_chunks: list[bytes] | None = None,
        hang_after: bool = False,
        returncode: int = 0,
    ) -> None:
        self._returncode: int | None = None
        self._final = returncode
        self.killed = False
        self.stdout = FakeStream(
            stdout_chunks, hang_after=hang_after, on_eof=self._exited
        )
        self.stderr = FakeStream(stderr_chunks or [])

    def _exited(self) -> None:
        if self._returncode is None:
            self._returncode = self._final

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def kill(self) -> None:
        self.killed = True
        self._returncode = self._final

    async def wait(self) -> int:
        if self._returncode is None:
            self._returncode = self._final
        return self._returncode


@pytest.fixture
def patched_spawn(monkeypatch: pytest.MonkeyPatch):
    """Replace ``create_subprocess_exec`` and hand back a factory + the record of calls."""

    calls: list[list[str]] = []
    holder: dict[str, FakeProcess] = {}

    async def fake_exec(*command: str, **kwargs: object) -> FakeProcess:
        calls.append(list(command))
        return holder["process"]

    import asyncio as aio

    monkeypatch.setattr(aio, "create_subprocess_exec", fake_exec)
    return calls, holder


def runtime(**kw: object) -> BbotRuntime:
    return BbotRuntime(**kw)  # type: ignore[arg-type]


SCAN = '{"type": "SCAN", "uuid": "scan-1", "name": "example.com"}'
EVENT = '{"type": "DNS_NAME", "uuid": "u-1", "host": "example.com", "data": "example.com"}'


# -- stderr --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stderr_is_drained_so_a_talky_tool_cannot_deadlock(patched_spawn) -> None:
    """The regression. Undrained stderr fills the pipe and the run hangs forever."""
    calls, holder = patched_spawn
    # Far more stderr than a pipe buffer holds.
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], stderr_chunks=[b"x" * 8192] * 64)
    rt = runtime(timeout=10.0)

    got = [a async for a in rt.acquire({"target": "example.com"})]

    assert len(got) == 1, "the reader must still make progress while stderr is noisy"
    assert holder["process"].killed is False


@pytest.mark.asyncio
async def test_stderr_tail_is_reported(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], stderr_chunks=[b"bbot: warning"])
    rt = runtime()
    [a async for a in rt.acquire({"target": "example.com"})]
    assert "bbot: warning" in rt.run.stderr_tail
    assert rt.run.stderr_bytes > 0


# -- deadline ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_deadline_kills_a_run_that_never_ends(patched_spawn) -> None:
    """A per-line timeout never fires while events keep arriving, so the scan is
    unbounded unless the deadline is on the run."""
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], hang_after=True, returncode=-9)
    rt = runtime(timeout=0.2)

    with pytest.raises(Exception) as exc:
        [a async for a in rt.acquire({"target": "example.com"})]

    assert "exceeded" in str(exc.value)
    assert holder["process"].killed is True
    assert rt.run.timed_out is True


@pytest.mark.asyncio
async def test_process_is_killed_when_the_consumer_stops_early(patched_spawn) -> None:
    """Breaking out of the generator must not leave a container running.

    ``aclose()`` is explicit because a ``break`` does not close an async generator
    synchronously -- the ``finally`` runs at close, which is exactly what a cancelled
    task does. Leaving it to the garbage collector would make the guarantee untested.
    """
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()] * 50, hang_after=True)
    rt = runtime(timeout=5.0)

    stream = rt.acquire({"target": "example.com"})
    async for _ in stream:
        break
    await stream.aclose()

    assert holder["process"].killed is True


# -- exit code -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_exit_code_is_recorded(patched_spawn) -> None:
    """Previously always None, because the manifest read a runtime nobody ran."""
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], returncode=0)
    rt = runtime()
    [a async for a in rt.acquire({"target": "example.com"})]
    assert rt.run.exit_code == 0
    assert rt.run.records == 1


@pytest.mark.asyncio
async def test_nonzero_exit_is_reported_not_hidden(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], returncode=2)
    rt = runtime()
    [a async for a in rt.acquire({"target": "example.com"})]
    assert rt.run.exit_code == 2


# -- quarantine ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_json_line_is_quarantined_not_dropped(patched_spawn) -> None:
    """A silent skip makes a broken BBOT build look exactly like a quiet one."""
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([b"not json at all\n", f"{EVENT}\n".encode()])
    rt = runtime()
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert len(got) == 1
    assert rt.run.quarantined
    assert rt.run.quarantined[0]["code"] == "non_json_stdout"
    assert rt.run.quarantined[0]["raw"] == "not json at all"


@pytest.mark.asyncio
async def test_malformed_json_is_quarantined(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([b'{"type": "DNS_NAME", broken\n'])
    rt = runtime()
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert got == []
    assert rt.run.quarantined[0]["code"] == "malformed_json"


@pytest.mark.asyncio
async def test_json_without_type_is_quarantined(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([b'{"no": "type"}\n'])
    rt = runtime()
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert got == []
    assert rt.run.quarantined[0]["code"] == "no_event_type"


@pytest.mark.asyncio
async def test_oversize_record_is_refused_and_counted(patched_spawn) -> None:
    """max_record_bytes used to be accepted and never applied."""
    calls, holder = patched_spawn
    big = b'{"type": "DNS_NAME", "data": "' + b"a" * 5000 + b'"}\n'
    holder["process"] = FakeProcess([big, f"{EVENT}\n".encode()])
    rt = runtime(max_record_bytes=1000)
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert len(got) == 1  # only the small one survives
    assert rt.run.truncated is True
    assert any(q["code"] == "record_too_large" for q in rt.run.quarantined)


# -- run metadata --------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_events_are_metadata_not_evidence(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{SCAN}\n".encode(), f"{EVENT}\n".encode()])
    rt = runtime()
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert len(got) == 1, "SCAN must not become an artifact"
    assert rt.scan_events and rt.scan_events[0]["type"] == "SCAN"
    assert rt.run.scan_events == 1


@pytest.mark.asyncio
async def test_scan_events_survive_an_early_break(patched_spawn) -> None:
    """Previously the SCAN list was extended after the loop, so a cut-short run lost
    exactly the metadata that explains why it was cut short."""
    calls, holder = patched_spawn
    holder["process"] = FakeProcess(
        [f"{SCAN}\n".encode()] + [f"{EVENT}\n".encode()] * 10, hang_after=True
    )
    rt = runtime(timeout=5.0)
    stream = rt.acquire({"target": "example.com"})
    async for _ in stream:
        break
    await stream.aclose()
    assert rt.scan_events, "scan metadata must survive early termination"


@pytest.mark.asyncio
async def test_reconcile_counters_add_up(patched_spawn) -> None:
    """§141's five numbers: seen, parsed, records, quarantined."""
    calls, holder = patched_spawn
    holder["process"] = FakeProcess(
        [b"junk\n", f"{SCAN}\n".encode(), f"{EVENT}\n".encode(), f"{EVENT}\n".encode()]
    )
    rt = runtime()
    got = [a async for a in rt.acquire({"target": "example.com"})]
    assert len(got) == 2
    assert rt.run.lines_seen == 4
    assert rt.run.records == 2
    assert rt.run.scan_events == 1
    assert len(rt.run.quarantined) == 1


@pytest.mark.asyncio
async def test_run_manifest_serialises(patched_spawn) -> None:
    calls, holder = patched_spawn
    holder["process"] = FakeProcess([f"{EVENT}\n".encode()], returncode=0)
    rt = runtime()
    [a async for a in rt.acquire({"target": "example.com"})]
    d = rt.run.to_dict()
    for key in ("argv", "exit_code", "records", "scan_events", "quarantined",
                "seconds", "timed_out", "truncated", "stderr_tail"):
        assert key in d
    assert d["image_digest"].startswith("sha256:")


def test_run_defaults_are_empty_not_null() -> None:
    r = BbotRun()
    assert r.exit_code is None
    assert r.quarantined == []
    assert r.to_dict()["records"] == 0
