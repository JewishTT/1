"""Feature — the primary-processing acceptance run, on a real page, for real.

Not a fixture. This fetches an actual HTML page over HTTP, runs it through
:class:`~parsers.primproc.PrimaryProcessor`, and prints the before and after with a byte
count for every reason the stage gives. Then it runs the same bytes through
:class:`~runtime.primproc.PrimProcRuntime` so the derived artefact, its locator and its
``derived_from`` chain are shown as they would be stored.

    live page
      -> raw bytes (what the source sent)
      -> PrimaryProcessor.process(body, content_type=...)
      -> cleaned text + a ledger that tiles the source
      -> PrimProcRuntime.acquire() -> original artefact + a derived artefact at primproc:<locator>

**§153 is honoured in the output, not just in the code.** If the fetch fails, the script says so at
the top, in the summary, and in the ``source`` field of the artefact it writes — it does not quietly
fall back to a fixture and let a reader assume the page came off the wire. The exit code differs
too: a fixture run exits ``6``, which a pipeline can fail on, while a live run exits ``0``.

Run it:

    uv run --project apps/interpretation python _prove_primproc.py
    uv run --project apps/interpretation python _prove_primproc.py --url https://example.com/

The fetch is the only thing here that touches the network. The cleaning stage itself opens no socket,
reads no clock and reads no environment beyond what it is handed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acquisition"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from domain.acquisition_artifact import AcquisitionArtifact
from runtime.primproc import (
    DERIVED_FROM_KEY,
    PrimProcRuntime,
)

from parsers.primproc import REMOVAL_REASONS, PrimaryProcessor

#: Tried in order. A page with a ``<script>``, a ``<style>``, navigation chrome and an ``<article>``
#: exercises every removal reason; a bare hello-world page would make the numbers look good for the
#: wrong reason, which is why ``example.com`` is last rather than first.
DEFAULT_URLS: tuple[str, ...] = (
    "https://en.wikipedia.org/wiki/Trestle",
    "https://www.python.org/",
    "https://example.com/",
)

FETCH_TIMEOUT = 20.0
MAX_BYTES = 4 * 1024 * 1024
USER_AGENT = "cognitive-primproc-proof/0.1 (+primary content processing acceptance run)"


@dataclass(frozen=True)
class Fetch:
    """What the wire gave us, or why it did not."""

    url: str
    ok: bool
    body: bytes
    content_type: str
    status: int
    detail: str

    @property
    def live(self) -> bool:
        return self.ok


def fetch(url: str) -> Fetch:
    """One HTTPS GET. No retries, no redirect chasing, no shell out."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            body = response.read(MAX_BYTES)
            return Fetch(
                url=url,
                ok=True,
                body=body,
                content_type=response.headers.get("Content-Type", "") or "",
                status=int(response.status),
                detail=f"HTTP {response.status}, {len(body)} bytes",
            )
    except urllib.error.HTTPError as exc:
        return Fetch(url, False, b"", "", int(exc.code), f"HTTPError: {exc}")
    except Exception as exc:  # noqa: BLE001 - reported plainly, never swallowed
        return Fetch(url, False, b"", "", 0, f"{type(exc).__name__}: {exc}")


def fetch_first(urls: tuple[str, ...]) -> Fetch:
    """The first URL that answers, and a report of every attempt either way."""
    attempts: list[str] = []
    for url in urls:
        got = fetch(url)
        attempts.append(f"{url} -> {'ok' if got.ok else got.detail}")
        if got.ok:
            return Fetch(
                url=got.url,
                ok=True,
                body=got.body,
                content_type=got.content_type,
                status=got.status,
                detail="; ".join(attempts),
            )
    return Fetch(
        url=urls[0],
        ok=False,
        body=b"",
        content_type="",
        status=0,
        detail="; ".join(attempts),
    )


def excerpt(text: str, limit: int = 700) -> str:
    """The first ``limit`` characters, with the tail cut on a line boundary where one is near."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = head.rfind("\n")
    return (head[:cut] if cut > limit // 2 else head) + "\n    … truncated for display"


def bar(value: int, total: int, width: int = 34) -> str:
    """A proportional bar, so the shape of the removals is visible and not just the numbers."""
    if total <= 0:
        return ""
    filled = round(width * value / total)
    return "#" * filled + "." * (width - filled)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", dest="urls", default=None)
    parser.add_argument("--out", default="artifacts/interpretation/primproc.json")
    args = parser.parse_args(argv)
    urls = tuple(args.urls) if args.urls else DEFAULT_URLS

    print("=" * 78)
    print("PRIMARY CONTENT PROCESSING - acceptance run")
    print("=" * 78)

    # -- §153: is this a live page or a fixture? Say so first, loudly. ---------
    print("\n0. INPUT PROVENANCE (§153)")
    got = fetch_first(urls)
    print(f"   candidates   : {len(urls)}")
    for attempt in got.detail.split("; "):
        print(f"   attempt      : {attempt}")
    if got.live:
        print(f"   INPUT IS A LIVE FETCH: {got.url}")
        print(f"   content_type : {got.content_type!r}")
        provenance = "live_fetch"
    else:
        print("   INPUT IS A LOCAL FIXTURE - THE LIVE FETCH FAILED.")
        print("   Nothing below was fetched over the network; the numbers describe the fixture only.")
        print("   Treat every rule that fired below as exercised on a fixture, not on a real page.")
        provenance = "local_fixture"
    print(f"   provenance   : {provenance}")

    # -- the stage -----------------------------------------------------------
    processor = PrimaryProcessor(probe_meta_charset=True)
    result = processor.process(got.body, content_type=got.content_type or "text/html")

    print("\n1. DECISION - which rule fired, and why it is knowable")
    print(f"   route            : {result.route}")
    print(f"   extract strategy : {result.strategy}")
    print(f"   decode rule      : {result.decode.rule}")
    print(f"   decode charset   : {result.decode.charset or '(none)'}")
    print(f"   declared header  : {result.decode.declared or '(none)'}")
    print(f"   media type       : {result.decode.media_type or '(none)'}")
    print(f"   meta probe       : declared={result.decode.probe_declared} "
          f"matched={result.decode.probe_matched} offset={result.decode.probe_offset}")
    print(f"   ok / refusal     : {result.ok} / {result.decode.refusal or '(none)'}")
    if not result.ok:
        print(f"   detail           : {result.decode.refusal_detail}")

    # The strategy the page's own markup earned, and what that region actually contained.
    # Printed because ``main`` and ``density`` are the two strategies that can be wrong in a
    # way the numbers do not show: a page whose <main> wraps the sidebar gets a confident
    # ``main`` and a cleaned text full of navigation. The reader is told which rule won and
    # given the region's opening tag so they can see the page agreed with it.
    if got.live:
        tag = b"article" if result.strategy == "article" else b"main"
        opening = b"<" + tag
        at = -1
        cursor = 0
        lowered = got.body.lower()
        while True:
            at = lowered.find(opening, cursor)
            if at < 0:
                break
            after = at + len(opening)
            if after >= len(got.body) or got.body[after : after + 1] in (b">", b" ", b"\t", b"\n", b"/"):
                break
            cursor = at + 1
        if at >= 0:
            snippet = got.body[at : at + 200].decode("utf-8", errors="replace").split(">")[0]
            print(f"   region opened by : {snippet[:150]}")
        print("   NOTE: the strategy order is the directive's (article, main, role=main,")
        print("         content-class, density). A page whose <main> wraps its chrome will be")
        print("         cleaned to chrome under a confident 'main' verdict. The strategy field")
        print("         is what makes that diagnosable rather than invisible.")

    print("\n2. SIZE")
    print(f"   input bytes      : {result.input_bytes}")
    print(f"   output bytes     : {result.output_bytes}")
    print(f"   source kept      : {result.source_bytes_kept}")
    print(f"   removed total    : {result.removed_bytes_total}")
    print(f"   entity expansion : {result.entity_expansion_bytes} output chars, "
          f"unescaped={result.unescaped}")
    print(f"   output lines     : {len(result.lines)}")
    reconciled = result.input_bytes == result.removed_bytes_total + result.source_bytes_kept
    print(f"   RECONCILES       : {reconciled}  "
          f"(input == removed + kept)")

    print("\n3. removed_bytes_by_reason - every transformation, counted")
    for reason in REMOVAL_REASONS:
        value = result.removed_bytes_by_reason[str(reason)]
        share = (100.0 * value / result.input_bytes) if result.input_bytes else 0.0
        print(f"   {reason!s:<20} {value:>9}  {share:5.1f}%  {bar(value, result.input_bytes)}")
    print(f"   {'TOTAL':<20} {result.removed_bytes_total:>9}")

    print("\n4. THE LEDGER - the source, rebuilt out of the spans that claim it")
    body = got.body
    rebuilt = b"".join(
        body[span.source_byte_start : span.source_byte_end] for span in result.ledger
    )
    print(f"   spans            : {len(result.ledger)}")
    print(f"   spans' bytes     : {sum(span.source_bytes for span in result.ledger)}")
    print(f"   REBUILDS SOURCE  : {rebuilt == body}")
    ledger_chars = sum(span.output_chars for span in result.ledger)
    line_chars = sum(len(line.text) for line in result.lines)
    print(f"   ledger out chars : {ledger_chars}")
    print(f"   line chars       : {line_chars}  "
          f"(differs by len(lines)-1 = {max(0, len(result.lines) - 1)}: the joins are synthesised)")

    print("\n5. BEFORE / AFTER")
    print("   ---- RAW (first 700 chars, as the source sent it) ----")
    print("    " + excerpt(body.decode("utf-8", errors="replace")).replace("\n", "\n    "))
    print("   ---- CLEANED ----")
    print("    " + excerpt(result.text).replace("\n", "\n    "))

    print("\n6. Raw <-> line mapping (every output line, named in raw bytes)")
    for line in result.lines[:12]:
        raw_slice = body[line.source_byte_start : line.source_byte_end]
        print(
            f"   line {line.line_number:>3}  out[{line.output_byte_start:>6},"
            f"{line.output_byte_end:>6})  src[{line.source_byte_start:>7},"
            f"{line.source_byte_end:>7})  {line.text[:52]!r}"
        )
        print(f"          raw    : {raw_slice.decode('utf-8', errors='replace')[:60]!r}")
    if len(result.lines) > 12:
        print(f"   … {len(result.lines) - 12} more lines")
    if result.lines:
        probe = body.index(b"python") if b"python" in body.lower() else None
        if probe is not None:
            print(f"   lookup: raw byte {probe} -> line "
                  f"{result.line_number_of_source_byte(probe)}")

    if result.notes:
        print("\n7. NOTES - what the parser saw that a well-formed page would not contain")
        for code in result.note_codes:
            print(f"   {code}")

    # -- the runtime decorator ------------------------------------------------
    print("\n8. THE RUNTIME CHAIN - original supplemented, not replaced")
    from datetime import UTC, datetime

    raw_artifact = AcquisitionArtifact(
        task_id="TSK-primproc-proof",
        source_id="proof.html",
        worker_ref="http",
        target_uri=got.url,
        locator="http:body:0",
        body=got.body,
        content_type=got.content_type or "text/html",
        fetched_at=datetime.now(UTC),
        transport="http",
        producer="proof-fetch",
        producer_version="0.1.0",
        metadata={"parser_hint": "raw_text"},
    )

    import asyncio

    async def run_chain() -> list[AcquisitionArtifact]:
        inner = _OneShot(raw_artifact)
        runtime = PrimProcRuntime(inner, processor=processor)
        stream = [item async for item in runtime.acquire({"task_id": "TSK-primproc-proof"})]
        print(f"   runtime_ref      : {runtime.runtime_ref} wrapping {runtime.inner_runtime_ref}")
        print(f"   capabilities     : {runtime.capabilities()}")
        print(f"   summary          : {json.dumps(runtime.summary())}")
        return stream

    stream = asyncio.run(run_chain())
    for item in stream:
        print(
            f"   {item.locator:<40} {item.byte_length:>8}B  "
            f"content_type={item.content_type!r}  producer={item.producer}  schema={item.schema}"
        )
    if len(stream) == 2:
        original, derived = stream
        provenance_record = derived.metadata[DERIVED_FROM_KEY]
        print("   derived_from     :")
        for key in (
            "locator",
            "capture_locator",
            "content_digest",
            "target_uri",
            "producer",
            "fetched_at",
            "observation_id",
            "capture_id",
        ):
            print(f"      {key:<16}: {provenance_record[key]}")
        print(f"      rule           : {derived.metadata['rule']}")
        print(f"      version        : {derived.metadata['primproc_version']}")
        print(f"      raw is intact  : {original.body == got.body}")
        print(f"      raw digest kept: {provenance_record['content_digest'] == original.record_digest()}")
        print(f"      digests differ : {derived.record_digest() != original.record_digest()}")

    # -- write the record -----------------------------------------------------
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "provenance": provenance,
        "url": got.url,
        "content_type": got.content_type,
        "fetch_detail": got.detail,
        "fetch_status": got.status,
        "result": result.to_dict(),
        "text": result.text,
        "lines": [line.to_dict() for line in result.lines],
        "ledger_tiles_source": rebuilt == body,
        "bytes_reconcile": reconciled,
        "artifacts": [item.to_dict() for item in stream],
    }
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n9. RECORD\n   written        : {out}")

    print("\n" + "=" * 78)
    if not got.live:
        print("RESULT: FIXTURE (the live fetch failed - see section 0). Not an acceptance run.")
        print("=" * 78)
        return 6
    ok = reconciled and rebuilt == body and len(stream) == 2
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(
        f"  live input={got.live}  bytes reconcile={reconciled}  "
        f"ledger tiles source={rebuilt == body}  chain supplemented={len(stream) == 2}"
    )
    print("=" * 78)
    return 0 if ok else 5


class _OneShot:
    """A one-artefact worker, so the decorator can be driven without a real runtime."""

    runtime_ref = "proof-fetch"
    execution_class = "api/http"

    def __init__(self, artifact: AcquisitionArtifact) -> None:
        self._artifact = artifact

    def capabilities(self) -> list[str]:
        return ["http"]

    def estimate(self, task: dict):  # pragma: no cover - the proof never estimates
        from runtime import CostEstimate

        return CostEstimate(expected_artifacts=1, expected_bytes=0, expected_seconds=0.0)

    async def acquire(self, task: dict):
        yield self._artifact

    async def aclose(self) -> None:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
