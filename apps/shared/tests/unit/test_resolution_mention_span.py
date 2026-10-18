"""ResolutionMention span survival (spec 030 T059/T060, contract 02 R5/R7).

The span used to be consumed into ``MentionOccurrenceKey.span``, hashed by
``mint_mention_id`` and then dropped. The only surviving trace was inside an irreversible
digest, so a merge decided on a mention could not be shown to an analyst against the
source. These pin that the span is now carried, and that an unlocatable one stays
unlocatable rather than being papered over with a zero.
"""

from __future__ import annotations

import pytest

from domain.mention_occurrence_index import MentionBindingError
from semantic.resolution import ResolutionMention

pytestmark = pytest.mark.unit


def _m(**kw) -> ResolutionMention:
    base = {"mention_id": "MN-test", "surface": "Acme"}
    base.update(kw)
    return ResolutionMention(**base)


class TestSpanIsCarried:
    def test_a_known_span_survives(self):
        m = _m(span=(10, 14), span_semantics="document_char")
        assert m.span == (10, 14)
        assert m.span_resolved is True

    def test_span_semantics_default_to_document_char_when_located(self):
        m = _m(span=(3, 9))
        assert m.span_semantics == "document_char"

    def test_segment_ref_is_carried_with_it(self):
        m = _m(span=(3, 9), segment_ref_for_span="SEG-abc")
        assert m.segment_ref_for_span == "SEG-abc"

    def test_position_zero_is_a_real_position(self):
        """0 must not be conflated with "not found"."""
        m = _m(span=(0, 4))
        assert m.span_resolved is True
        assert m.span == (0, 4)


class TestUnlocatableStaysUnlocatable:
    def test_no_span_is_unlocated(self):
        m = _m()
        assert m.span is None
        assert m.span_resolved is False
        assert m.span_semantics == "unlocated"

    def test_negative_span_does_not_claim_to_be_resolved(self):
        """-1 is the extractor's explicit 'I could not locate this'."""
        m = _m(span=(-1, -1))
        assert m.span_resolved is False
        assert m.span_semantics == "unlocated"
        assert m.span_reason is not None

    def test_a_caller_cannot_force_unlocated_semantics_onto_a_real_span(self):
        m = _m(span=(0, 0), span_semantics="unlocated")
        assert m.span_semantics == "document_char"
        assert m.span_resolved is True

    def test_caller_reason_is_preserved_when_given(self):
        m = _m(span=(-1, -1), span_reason="segment had no document-absolute offset")
        assert m.span_reason == "segment had no document-absolute offset"


class TestInvalidSpansAreRefused:
    def test_backwards_span_is_refused(self):
        with pytest.raises(MentionBindingError) as e:
            _m(span=(9, 3))
        assert (
            e.value.args[0] == "[resolution_mention_span_invalid] end 3 precedes start 9; "
            "a span read backwards addresses nothing"
        )

    def test_refusal_names_both_ends(self):
        with pytest.raises(MentionBindingError) as e:
            _m(span=(50, 2))
        assert "50" in str(e.value) and "2" in str(e.value)


class TestBackwardsCompatibility:
    """Existing construction sites must keep working unchanged."""

    def test_the_old_construction_shape_still_builds(self):
        """Exactly the keyword set document_adapter.py used before T059."""
        m = ResolutionMention(
            mention_id="MN-old",
            surface="Acme",
            kind="org",
            tenant_id="t",
            investigation_id="INV-1",
            source_id="src-1",
            source_family="web",
            independence_group="ig-1",
            declared_type_refs=("schema:Organization",),
        )
        assert m.mention_id == "MN-old"
        assert m.span is None
        assert m.span_resolved is False

    def test_frozen_dataclass_is_still_frozen(self):
        import dataclasses

        m = _m(span=(1, 2))
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.surface = "mutated"  # type: ignore[misc]

    def test_type_refs_are_unaffected_by_the_new_fields(self):
        from semantic.contracts import SemanticRef, TypeAssertion

        m = _m(
            span=(1, 5),
            declared_type_refs=("schema:Org",),
            type_assertions=(
                TypeAssertion(type_ref="schema:Person", type_scheme=SemanticRef.INTERNAL),
            ),
        )
        pairs = m.type_refs()
        assert any(r[0] == "schema:Person" for r in pairs)
        assert any(r[0] == "schema:Org" for r in pairs)
        assert m.type_hint_source() == "assertion"
