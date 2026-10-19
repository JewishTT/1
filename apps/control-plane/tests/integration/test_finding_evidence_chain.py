"""A finding's evidence chain is resolved, not rendered (FR-016, WP5).

The finding view used to report a single boolean, ``evidence_resolves``, computed from
whether its observations were marked immutable. That answers "were the rows immutable?"
— not "does this citation still point at the bytes that produced it?".

The chain is now stored as serialised `EvidenceSpanRef`s and rehydrated on read. These
tests pin the three outcomes and, more importantly, the rule that an empty chain is
**unresolved**, never grounded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.main import app
from api.routes.findings import FND_5001_EVIDENCE
from services.catalog import Catalog, FindingRecord

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _finding(chain: list[dict] | None = None) -> str:
    catalog = Catalog()
    catalog.put_finding(
        FindingRecord(
            finding_id="FND-T1",
            why_detected="test",
            evidence_chain=chain or [],
        )
    )
    return catalog.finding("FND-T1")


# ---------------------------------------------------------------------------
# Through the API, on the seeded finding
# ---------------------------------------------------------------------------


def test_the_seeded_finding_reports_a_grounded_chain(client: TestClient) -> None:
    body = client.get("/api/v1/findings/FND-5001").json()

    assert body["evidence_chain_status"] == "grounded"
    assert body["evidence_chain_problems"] == []
    assert len(body["evidence_chain"]) == 2
    assert {span["observation_ref"] for span in body["evidence_chain"]} == {"OBS-1001", "OBS-1002"}


def test_every_returned_span_can_address_its_bytes(client: TestClient) -> None:
    """The round trip proves the reader can rebuild what the writer stored."""
    body = client.get("/api/v1/findings/FND-5001").json()

    for span in body["evidence_chain"]:
        assert span["selector_semantics_version"].count("/") == 1
        assert span["blob_digest"].startswith("sha256:")
        assert len(span["blob_digest"]) == len("sha256:") + 64
        assert span["source_locator"]["uri"]
        assert span["span_id"].startswith("sha256:")


def test_the_fixture_spans_are_the_typed_objects_not_dicts() -> None:
    # The fixture serialises through the contract's own `as_dict`, so a shape the
    # reader would refuse cannot enter the seed data in the first place.
    for span in FND_5001_EVIDENCE:
        assert span.as_dict()["span_id"] == span.content_key()


# ---------------------------------------------------------------------------
# The three outcomes, on a synthetic catalog
# ---------------------------------------------------------------------------


def test_an_empty_chain_is_unresolved_not_grounded() -> None:
    view = _finding([])

    assert view["evidence_chain_status"] == "unresolved", (
        "a finding with no spans has nothing that grounds it; reporting that as grounded is "
        "the exact claim FR-016 exists to prevent"
    )
    assert view["evidence_chain"] == []


def test_a_half_rebuildable_chain_is_partial_and_names_what_failed() -> None:
    good = FND_5001_EVIDENCE[0].as_dict()
    broken = {
        "observation_ref": "OBS-1002",
        "blob_digest": "sha256:" + "b" * 64,
        # a selector that is not one of the eight kinds
        "selector": {"byte_offset": {"start": 1, "end": 2}},
        "source_locator": {"uri": "http://fixtures.local/ledger.html", "fragment": ""},
        "selector_semantics_version": "char_span/1",
    }

    view = _finding([good, broken])

    assert view["evidence_chain_status"] == "partial"
    assert len(view["evidence_chain"]) == 1
    assert view["evidence_chain_problems"], "a failed entry must say why it failed"
    assert view["evidence_chain_problems"][0]["index"] == 1
    assert "unknown selector kind" in view["evidence_chain_problems"][0]["reason"]


def test_a_chain_of_only_broken_entries_is_unresolved() -> None:
    broken = {"observation_ref": "OB-1", "selector": {"nope": {}}}
    view = _finding([broken])

    assert view["evidence_chain_status"] == "unresolved"
    assert len(view["evidence_chain_problems"]) == 1


def test_a_tampered_span_id_is_reported_not_hidden() -> None:
    tampered = FND_5001_EVIDENCE[0].as_dict()
    tampered["span_id"] = "sha256:" + "f" * 64

    view = _finding([tampered])

    assert view["evidence_chain_status"] == "unresolved"
    assert "span_id" in view["evidence_chain_problems"][0]["reason"]
