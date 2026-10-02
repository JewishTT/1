"""The ``primproc`` decorator: it supplements, it does not replace, and it mints nothing.

Three things this file is about, in the order the directive names them.

*Supplementation.* Every artefact the wrapped runtime yields is still yielded, unchanged, and the
cleaned one follows it. :class:`TestSupplements` asserts that on a stream where **every** artefact
is a cleaning route, so a "replace" implementation would fail loudly rather than pass by accident on
a payload that happened to be JSON.

*Provenance.* :class:`TestProvenance` reads the derived artefact's ``derived_from`` record and
checks that everything in it is a **fact about the original** — locator, digest, target URI, task,
source, producer, fetch time — and that the two identities the sink mints downstream are present
only when a caller supplied them and are empty strings otherwise rather than plausible-looking
guesses.

*§3.* :class:`TestBoundary` asserts that no field on the derived artefact can hold an entity, a
claim, a type or a relation, and that a JSON payload produces **no** derived artefact at all — the
stage has no opinion about it, and minting a supplement nobody asked for would be a second address
over bytes that did not change.

The real cleaning stage is used throughout rather than a stand-in, because the decorator's contract
includes the stage's ``artifact_body()``, ``removed_bytes_total`` and ``note_codes``. The sibling
app is put on ``sys.path`` explicitly, and one test uses a stand-in processor so the decorator's own
logic is provable without the interpretation tree.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[2]
for _path in (_APPS, _APPS / "interpretation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from domain.acquisition_artifact import AcquisitionArtifact  # noqa: E402
from runtime import CostEstimate, RuntimeError_  # noqa: E402
from runtime.primproc import (  # noqa: E402
    CLEANED_PARSER_HINT,
    DERIVED_FROM_KEY,
    DERIVED_TRANSPORT,
    PRIMPROC_LOCATOR_PREFIX,
    PRIMPROC_RUNTIME_REF,
    PrimProcRuntime,
    cleaned_locator,
    primary_processor,
)

FETCHED_AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

PAGE = (
    b"<!DOCTYPE html><html><head><title>T</title></head><body>"
    b"<script>evil()</script><nav>chrome</nav>"
    b"<article><p>Real   content.</p><p>Second para.</p></article></body></html>"
)


def artifact(
    body: bytes = PAGE,
    *,
    locator: str = "http:page:1",
    content_type: str | None = "text/html",
    metadata: dict | None = None,
) -> AcquisitionArtifact:
    return AcquisitionArtifact(
        task_id="TSK-primproc-1",
        source_id="fixture.html",
        worker_ref="http",
        target_uri="https://example.invalid/page",
        locator=locator,
        body=body,
        content_type=content_type,
        fetched_at=FETCHED_AT,
        transport="http",
        producer="fixture",
        producer_version="1.0.0",
        metadata=metadata or {"parser_hint": "raw_text"},
    )


class ScriptedRuntime:
    """A minimal ``AcquisitionWorker`` that yields a fixed list of artefacts."""

    runtime_ref = "scripted"
    execution_class = "api/http"

    def __init__(self, artifacts: list[AcquisitionArtifact]) -> None:
        self._artifacts = artifacts
        self.tasks: list[dict] = []
        self.closed = 0

    def capabilities(self) -> list[str]:
        return ["http", "fixture"]

    def estimate(self, task: dict) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=len(self._artifacts), expected_bytes=1024, expected_seconds=1.0
        )

    async def acquire(self, task: dict) -> AsyncIterator[AcquisitionArtifact]:
        self.tasks.append(task)
        for item in self._artifacts:
            yield item

    async def aclose(self) -> None:
        self.closed += 1


async def drain(runtime: PrimProcRuntime, task: dict | None = None) -> list[AcquisitionArtifact]:
    task = task or {"task_id": "TSK-primproc-1", "source_id": "fixture.html"}
    return [item async for item in runtime.acquire(task)]


def decorated(artifacts: list[AcquisitionArtifact], **kwargs) -> tuple[
    PrimProcRuntime, ScriptedRuntime
]:
    inner = ScriptedRuntime(artifacts)
    return PrimProcRuntime(inner, **kwargs), inner


class TestSupplements:
    @pytest.mark.asyncio
    async def test_the_original_is_still_produced_and_the_cleaned_one_follows_it(self):
        runtime, _ = decorated([artifact()])
        stream = await drain(runtime)
        assert [item.locator for item in stream] == [
            "http:page:1",
            f"{PRIMPROC_LOCATOR_PREFIX}http:page:1",
        ]
        assert stream[0].body == PAGE
        assert stream[0].content_type == "text/html"
        assert stream[0].producer == "fixture"

    @pytest.mark.asyncio
    async def test_supplementation_holds_when_every_artefact_is_a_cleaning_route(self):
        """The case that catches a "replace" implementation.

        Three HTML artefacts in, six out: every original untouched, each immediately followed by its
        own supplement. An implementation that swapped the raw for the cleaned would produce three
        artefacts and pass every test that used a single JSON payload. The order is *interleaved*
        rather than grouped, which is the streaming contract — and the next test asserts it.
        """
        originals = [artifact(locator=f"http:page:{index}") for index in range(1, 4)]
        runtime, _ = decorated(originals)
        stream = await drain(runtime)
        expected = []
        for original in originals:
            expected.append(original.locator)
            expected.append(f"{PRIMPROC_LOCATOR_PREFIX}{original.locator}")
        assert [item.locator for item in stream] == expected
        assert len(stream) == 6
        assert [stream[0].body, stream[2].body, stream[4].body] == [
            item.body for item in originals
        ]

    @pytest.mark.asyncio
    async def test_the_original_comes_first_so_a_sink_has_its_addresses_first(self):
        runtime, _ = decorated([artifact()])
        stream = await drain(runtime)
        provenance = stream[1].metadata[DERIVED_FROM_KEY]
        assert provenance["locator"] == stream[0].locator

    @pytest.mark.asyncio
    async def test_a_non_cleaning_route_produces_no_supplement_at_all(self):
        runtime, _ = decorated([artifact(b'{"a":1}', content_type="application/json")])
        stream = await drain(runtime)
        assert len(stream) == 1
        assert stream[0].locator == "http:page:1"
        assert runtime.derived == ()
        assert runtime.refusals == ()

    @pytest.mark.asyncio
    async def test_the_stream_is_not_buffered(self):
        """One artefact in, two out, before the second original is even produced.

        §5 and §36: a decorator that collected the run and cleaned at the end would hold every body
        in memory at once, which is the unboundedness the streaming contract exists to prevent. The
        scripted runtime records how far it got when each artefact was pulled.
        """
        produced: list[str] = []

        class Counting(ScriptedRuntime):
            async def acquire(self, task):
                self.tasks.append(task)
                for index in (1, 2):
                    produced.append(f"emitted-{index}")
                    yield artifact(locator=f"http:page:{index}")

        inner = Counting([artifact()])
        runtime = PrimProcRuntime(inner)
        seen: list[str] = []
        async for item in runtime.acquire({"task_id": "T"}):
            seen.append(item.locator)
            if item.locator.endswith(":1"):
                assert produced == ["emitted-1"], "the second original was produced too early"
        assert seen == [
            "http:page:1",
            f"{PRIMPROC_LOCATOR_PREFIX}http:page:1",
            "http:page:2",
            f"{PRIMPROC_LOCATOR_PREFIX}http:page:2",
        ]

    @pytest.mark.asyncio
    async def test_a_refused_decode_yields_the_original_and_records_a_code(self):
        """A mis-encoded page must not cost the run its raw bytes.

        §98's failure class in a new place: an exception here would abandon a run over one page and
        lose the artefacts that were fine. So the refusal is recorded on the runtime, the original
        is still yielded, and no supplement is emitted.
        """
        runtime, _ = decorated([artifact("<p>Анна</p>".encode("windows-1251"))])
        stream = await drain(runtime)
        assert len(stream) == 1
        assert stream[0].body == "<p>Анна</p>".encode("windows-1251")
        assert len(runtime.refusals) == 1
        assert runtime.refusals[0].code == "decode_charset_undeclared_and_undecodable"
        assert runtime.refusals[0].locator == "http:page:1"
        assert runtime.derived == ()

    @pytest.mark.asyncio
    async def test_a_stage_that_raises_is_recorded_and_the_run_continues(self):
        class Exploding:
            def process(self, body, *, content_type=None):
                raise ValueError("boom")

            def is_cleaning_route(self, content_type):
                return True

            version = "x"
            schema = "y"

        runtime, _ = decorated([artifact()], processor=Exploding())
        stream = await drain(runtime)
        assert len(stream) == 1
        assert runtime.refusals[0].code == "primproc_raised"
        assert "ValueError" in runtime.refusals[0].detail

    @pytest.mark.asyncio
    async def test_a_second_bad_page_does_not_stop_a_good_one(self):
        bad = artifact("<p>Анна</p>".encode("windows-1251"), locator="http:page:1")
        good = artifact(locator="http:page:2")
        runtime, _ = decorated([bad, good])
        stream = await drain(runtime)
        assert len(stream) == 3
        assert stream[2].locator == f"{PRIMPROC_LOCATOR_PREFIX}http:page:2"
        assert len(runtime.refusals) == 1


class TestProvenance:
    @pytest.mark.asyncio
    async def test_the_derivation_record_carries_only_facts_about_the_original(self):
        runtime, _ = decorated([artifact(metadata={"parser_hint": "raw_text"})])
        stream = await drain(runtime)
        original, derived = stream
        provenance = derived.metadata[DERIVED_FROM_KEY]
        assert provenance["locator"] == original.locator
        assert provenance["capture_locator"] == original.effective_capture_locator()
        assert provenance["content_digest"] == original.record_digest()
        assert provenance["target_uri"] == original.target_uri
        assert provenance["task_id"] == original.task_id
        assert provenance["source_id"] == original.source_id
        assert provenance["worker_ref"] == original.worker_ref
        assert provenance["producer"] == original.producer
        assert provenance["producer_version"] == original.producer_version
        assert provenance["content_type"] == "text/html"
        assert provenance["transport"] == "http"
        assert provenance["fetched_at"] == original.fetched_at.isoformat()
        assert provenance["parser_hint"] == "raw_text"

    @pytest.mark.asyncio
    async def test_the_two_sink_minted_identities_are_empty_rather_than_guessed(self):
        """A runtime decorator stands **upstream** of the sink and cannot know them.

        So they are empty strings, and a consumer can rebuild them from what is there:
        ``observation_id_for(tenant_id, capture_id, locator, record_digest)`` is a pure function and
        every input except ``tenant_id`` is on the record. A plausible-looking invented id would be
        worse than an admitted gap — it would join to nothing and look like it joined.
        """
        runtime, _ = decorated([artifact()])
        stream = await drain(runtime)
        provenance = stream[1].metadata[DERIVED_FROM_KEY]
        assert provenance["observation_id"] == ""
        assert provenance["capture_id"] == ""

    @pytest.mark.asyncio
    async def test_a_supplied_resolver_fills_them_in(self):
        runtime, _ = decorated(
            [artifact()],
            identity_resolver=lambda art: {
                "observation_id": "OBS-parent",
                "capture_id": "CAP-parent",
            },
        )
        stream = await drain(runtime)
        provenance = stream[1].metadata[DERIVED_FROM_KEY]
        assert provenance["observation_id"] == "OBS-parent"
        assert provenance["capture_id"] == "CAP-parent"

    @pytest.mark.asyncio
    async def test_the_locator_is_the_family_scheme_over_the_original_locator(self):
        runtime, _ = decorated([artifact(locator="searxng:page:3")])
        stream = await drain(runtime)
        assert stream[1].locator == "primproc:searxng:page:3"
        assert cleaned_locator(stream[0]) == "primproc:searxng:page:3"

    @pytest.mark.asyncio
    async def test_the_derived_artefact_is_its_own_capture(self):
        """Cleaned bytes did not come back from the source, so they are not that source's capture.

        §20: a capture is what physically came back. Sharing the original's capture locator would
        put two digests under one capture identity, and the capture's ``content_digest`` would then
        describe neither.
        """
        runtime, _ = decorated([artifact()])
        stream = await drain(runtime)
        original, derived = stream
        assert derived.capture_locator is None
        assert derived.effective_capture_locator() == derived.locator
        assert derived.effective_capture_locator() != original.effective_capture_locator()
        assert derived.record_digest() != original.record_digest()

    @pytest.mark.asyncio
    async def test_a_record_inside_a_shared_capture_keeps_naming_its_capture(self):
        """A per-record artefact's ``capture_locator`` is preserved on the *derivation record*.

        The derived artefact is its own capture; the derivation record still says which capture the
        original belonged to, which is the join a consumer needs.
        """
        original = artifact()
        shared = AcquisitionArtifact(
            task_id=original.task_id,
            source_id=original.source_id,
            worker_ref=original.worker_ref,
            target_uri=original.target_uri,
            locator="json:results[0]",
            capture_locator="http:page:1",
            body=original.body,
            content_type=original.content_type,
            fetched_at=original.fetched_at,
            transport=original.transport,
            producer=original.producer,
            producer_version=original.producer_version,
        )
        runtime, _ = decorated([shared])
        stream = await drain(runtime)
        assert stream[1].metadata[DERIVED_FROM_KEY]["capture_locator"] == "http:page:1"

    @pytest.mark.asyncio
    async def test_the_version_and_the_rule_that_decided_are_both_on_the_record(self):
        """§133's "raw through parser v1 versus v2" needs a place for the version to live.

        Four places, deliberately: ``producer_version`` (attribution),
        ``metadata["primproc_version"]`` (the stage's own claim),
        ``metadata["rule"]`` (which extraction strategy won) and ``schema`` (the record shape).
        """
        runtime, _ = decorated([artifact()])
        derived = (await drain(runtime))[1]
        assert derived.producer == PRIMPROC_RUNTIME_REF
        assert derived.producer_version == derived.metadata["primproc_version"]
        assert derived.metadata["rule"] == "article"
        assert derived.metadata["decode_rule"] == "utf8_default"
        assert derived.metadata["content_route"] == "html"
        assert derived.schema == f"{derived.metadata['primproc_schema']}+primproc-1"

    @pytest.mark.asyncio
    async def test_the_removals_are_on_the_record_in_full(self):
        runtime, _ = decorated([artifact()])
        derived = (await drain(runtime))[1]
        removals = derived.metadata["removed_bytes_by_reason"]
        head = "<head><title>T</title></head>"
        assert removals["skip_element"] == len(head) + len("<script>evil()</script>")
        assert removals["markup_declaration"] == len("<!DOCTYPE html>")
        assert removals["outside_main"] == len("chrome")
        assert removals["whitespace"] == 2
        assert set(removals) == {
            "skip_element",
            "html_comment",
            "markup_declaration",
            "attribute",
            "outside_main",
            "element_markup",
            "whitespace",
        }
        assert derived.metadata["removed_bytes_total"] == sum(removals.values())
        assert (
            derived.metadata["source_bytes_kept"] + derived.metadata["removed_bytes_total"]
            == len(PAGE)
        )

    @pytest.mark.asyncio
    async def test_the_content_type_says_what_the_bytes_now_are(self):
        """``text/plain; charset=utf-8``, not ``text/html``.

        Declaring the original's type would send a consumer's parser back through markup parsing on
        bytes that no longer contain markup — and would make the media type a false statement about
        the artefact.
        """
        runtime, _ = decorated([artifact()])
        derived = (await drain(runtime))[1]
        assert derived.content_type == "text/plain; charset=utf-8"
        assert derived.metadata["parser_hint"] == CLEANED_PARSER_HINT
        assert derived.transport == DERIVED_TRANSPORT
        assert derived.body.decode("utf-8").startswith("Real content.")

    @pytest.mark.asyncio
    async def test_notes_reach_the_record_so_a_malformed_page_is_visible_downstream(self):
        runtime, _ = decorated([artifact(b"<p>trunc")])
        derived = (await drain(runtime))[1]
        assert "html_unclosed_element" in derived.metadata["notes"]

    @pytest.mark.asyncio
    async def test_the_fetch_time_is_the_originals_and_no_clock_is_read(self):
        """The original's ``fetched_at``, and ``datetime`` never constructed here.

        Deriving text now does not move when the bytes were fetched, and reusing the original's
        timestamp keeps a clock off this path. A ``datetime.now(UTC)`` here would make the derived
        artefact's identity depend on when the run happened.
        """
        import datetime as datetime_module

        runtime, _ = decorated([artifact()])
        derived = (await drain(runtime))[1]
        assert derived.fetched_at == FETCHED_AT

        source = (
            Path(__file__).resolve().parents[2] / "runtime" / "primproc.py"
        ).read_text(encoding="utf-8")
        assert "datetime.now" not in source
        assert "utcnow" not in source
        assert "from datetime import" not in source
        assert datetime_module.datetime.now is not None


class TestBoundary:
    @pytest.mark.asyncio
    async def test_no_field_on_the_derived_artefact_can_hold_a_semantic_judgement(self):
        """§3 by shape: the artefact's own fields, not just the nested metadata.

        ``AcquisitionArtifact`` has no entity, claim, type, confidence or relation field, and this
        decorator does not add one to ``metadata`` either. Checked over the metadata keys as exact
        names, because ``removed_bytes_by_reason`` contains no forbidden word but the count
        ``entity_expansion_bytes`` does — and that is a count of output bytes.
        """
        runtime, _ = decorated([artifact()])
        derived = (await drain(runtime))[1]
        forbidden = {
            "entity",
            "entity_id",
            "entity_type",
            "mention",
            "mention_id",
            "claim",
            "claim_id",
            "relation",
            "relation_id",
            "resolution",
            "type",
            "confidence",
            "score",
            "salience",
        }
        assert not forbidden & set(derived.metadata)
        assert not forbidden & set(derived.to_dict())
        assert not forbidden & set(derived.metadata[DERIVED_FROM_KEY])

    @pytest.mark.asyncio
    async def test_a_json_payload_gets_no_artefact_of_its_own_kind(self):
        """The stage declines to have an opinion about JSON, and mints nothing about it either.

        §3's other half: not minting a *cleaner* address over bytes that did not change is as much a
        boundary as not minting an entity.
        """
        for body, content_type in (
            (b'{"a":1}', "application/json"),
            (b'{"a":1}\n', "application/x-ndjson"),
            (b"just words", "text/plain"),
            (b"\x89PNG not really", "image/png"),
        ):
            runtime, _ = decorated([artifact(body, content_type=content_type)])
            stream = await drain(runtime)
            assert len(stream) == 1, content_type
            assert runtime.derived == ()

    @pytest.mark.asyncio
    async def test_the_xml_route_is_a_cleaning_route_too(self):
        runtime, _ = decorated(
            [
                artifact(
                    b"<rss><channel><item><title>Entry</title></item></channel></rss>",
                    content_type="application/rss+xml",
                )
            ]
        )
        stream = await drain(runtime)
        assert len(stream) == 2
        assert "Entry" in stream[1].body.decode("utf-8")


class TestContract:
    def test_it_refuses_something_that_is_not_a_worker(self):
        with pytest.raises(RuntimeError_) as caught:
            PrimProcRuntime(object())
        assert caught.value.code == "runtime_protocol_invalid"

    def test_the_capabilities_are_the_wrapped_ones_plus_one(self):
        runtime, _ = decorated([artifact()])
        assert runtime.capabilities() == ["http", "fixture", "content-primary-processing"]

    def test_the_estimate_is_the_wrapped_one_doubled_and_says_why(self):
        """Upper bounds, not estimates: at most one supplement per artefact, never larger than its
        source. A scheduler budgeting on them is never surprised."""
        runtime, _ = decorated([artifact()])
        estimate = runtime.estimate({"task_id": "T"})
        assert estimate.expected_artifacts == 2
        assert estimate.expected_bytes == 2048
        assert estimate.expected_seconds == 1.0

    def test_the_runtime_ref_is_this_stage_and_the_wrapped_ref_is_kept_beside_it(self):
        runtime, inner = decorated([artifact()])
        assert runtime.runtime_ref == PRIMPROC_RUNTIME_REF
        assert runtime.inner_runtime_ref == inner.runtime_ref
        assert runtime.execution_class == inner.execution_class

    @pytest.mark.asyncio
    async def test_aclose_reaches_the_wrapped_runtime(self):
        runtime, inner = decorated([artifact()])
        await runtime.aclose()
        assert inner.closed == 1

    @pytest.mark.asyncio
    async def test_the_task_reaches_the_wrapped_runtime_unchanged(self):
        runtime, inner = decorated([artifact()])
        task = {"task_id": "TSK-primproc-1", "source_id": "fixture.html", "worker_ref": "http"}
        await drain(runtime, task)
        assert inner.tasks == [task]

    @pytest.mark.asyncio
    async def test_the_summary_reports_the_stage_version_and_both_counts(self):
        runtime, _ = decorated([artifact()])
        await drain(runtime)
        summary = runtime.summary()
        assert summary["runtime_ref"] == PRIMPROC_RUNTIME_REF
        assert summary["inner_runtime_ref"] == "scripted"
        assert summary["primproc_version"] == "primproc-1"
        assert summary["derived"] == 1
        assert summary["refusals"] == []

    @pytest.mark.asyncio
    async def test_a_stand_in_processor_can_drive_the_decorator(self):
        """The decorator's own logic is provable without the interpretation tree on the path.

        Which is the point of :class:`~runtime.primproc.PrimaryProcessorPort`: the decorator depends
        on four members, not on the whole stage.
        """

        class Stand:
            version = "stand-1"
            schema = "stand/v1"

            def is_cleaning_route(self, content_type):
                return content_type == "text/html"

            def process(self, body, *, content_type=None):
                class Result:
                    ok = True
                    version = "stand-1"
                    schema = "stand/v1"
                    route = "html"
                    strategy = "article"
                    text = "cleaned"
                    entity_expansion_bytes = 0
                    unescaped = False
                    note_codes = ()
                    lines = ()
                    removed_bytes_by_reason = {"element_markup": len(body)}
                    removed_bytes_total = len(body)
                    source_bytes_kept = 0

                    def artifact_body(self):
                        return b"cleaned"

                return Result()

        runtime, _ = decorated([artifact()], processor=Stand())
        derived = (await drain(runtime))[1]
        assert derived.body == b"cleaned"
        assert derived.producer_version == "stand-1"
        assert derived.schema == "stand/v1+stand-1"

    def test_the_real_processor_factory_returns_the_real_stage(self):
        processor = primary_processor()
        assert processor.version == "primproc-1"
        assert processor.schema == "primary-content/v1"
        assert processor.is_cleaning_route("text/html") is True

    @pytest.mark.asyncio
    async def test_the_decorator_satisfies_the_worker_protocol(self):
        runtime, _ = decorated([artifact()])
        for member in ("runtime_ref", "execution_class", "capabilities", "estimate", "acquire"):
            assert hasattr(runtime, member), member
        assert asyncio.iscoroutinefunction(runtime.aclose)
