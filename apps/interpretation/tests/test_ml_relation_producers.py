from __future__ import annotations

from domain.signal_basis import SignalBasis
from extractors.signals.ml import (
    GLiNERRelexExtractor,
    StanfordOpenIEExtractor,
    gliner_relex_signals,
    stanford_openie_signals,
)
from extractors.signals.protocol import ExtractionScope
from extractors.signals.signal import SignalKind


class FakeGLiNER:
    def __init__(self, output):
        self.output, self.calls = output, []

    def inference(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return self.output


def _scope():
    return ExtractionScope(tenant_id="tenant-test", context_ref="CTX-test",
                           semantic_regime_ref="REG-test", document_ref="CAP-test",
                           investigation_id="CASE-test")


def test_gliner_relex_emits_source_grounded_signal_through_registry():
    text = "Dr. Ada Lovelace works for Analytical Engines Ltd."
    entities = [[
        {"start": 4, "end": 16, "text": "Ada Lovelace", "label": "person", "score": 0.97},
        {"start": 27, "end": 50, "text": "Analytical Engines Ltd.", "label": "organization", "score": 0.95},
    ]]
    relations = [[{"head": {"entity_idx": 0}, "tail": {"entity_idx": 1},
                   "relation": "works for", "score": 0.91}]]
    model = FakeGLiNER((entities, relations))
    extractor = GLiNERRelexExtractor(model, model_ref="test/relex")
    report = extractor.report(text, scope=_scope())
    assert len(report.signals) == 1
    assert report.refusals == ()
    signal = report.signals[0]
    assert signal.relation_surface == "works for"
    assert signal.basis is SignalBasis.PREDICATE_TEXT
    assert signal.kind is SignalKind.SEMANTIC
    assert signal.producer_confidence == 0.91
    assert signal.producer_ref == "ml/gliner-relex"
    assert signal.capture_ref == "CAP-test"
    assert signal.relation_ref is None
    assert model.calls[0][1]["relation_threshold"] == 0.65
    assert extractor.declares().independence_family == "relation-ml-producers"
    stamped = gliner_relex_signals([text], scope=_scope(), extractor=extractor)
    assert len(stamped) == 1
    assert stamped[0].signal_id == signal.signal_id


def test_gliner_unverifiable_model_label_is_a_refusal_not_a_fabricated_quote():
    text = "Ada Lovelace joined Analytical Engines Ltd."
    entities = [[
        {"start": 0, "end": 12, "text": "Ada Lovelace", "label": "person", "score": 0.99},
        {"start": 20, "end": 43, "text": "Analytical Engines Ltd.", "label": "organization", "score": 0.99},
    ]]
    relations = [[{"head": {"entity_idx": 0}, "tail": {"entity_idx": 1},
                   "relation": "works for", "score": 0.9}]]
    report = GLiNERRelexExtractor(FakeGLiNER((entities, relations))).report(text, scope=_scope())
    assert report.signals == ()
    assert [item.code for item in report.refusals] == ["prediction_not_source_grounded"]



def test_gliner_refuses_multiple_matching_predicate_spans_in_one_neighbourhood():
    text = "Ada founded founded Beta."
    entities = [[
        {"start": 0, "end": 3, "text": "Ada", "label": "person", "score": 0.99},
        {"start": 20, "end": 24, "text": "Beta", "label": "organization", "score": 0.99},
    ]]
    relations = [[{"head": {"entity_idx": 0}, "tail": {"entity_idx": 1},
                   "relation": "founded", "score": 0.9}]]
    report = GLiNERRelexExtractor(FakeGLiNER((entities, relations))).report(
        text, scope=_scope()
    )
    assert report.signals == ()
    assert report.refusals[0].code == "prediction_not_source_grounded"

def test_gliner_refuses_oversized_text_before_model_call():
    model = FakeGLiNER(([[]], [[]]))
    report = GLiNERRelexExtractor(model, max_document_chars=4).report("too long", scope=_scope())
    assert report.signals == ()
    assert report.refusals[0].code == "document_exceeds_character_ceiling"
    assert model.calls == []


def test_stanford_openie_parses_tsv_and_emits_grounded_signal():
    text = "Ada Lovelace works for Analytical Engines Ltd."
    def runner(command, submitted, timeout):
        assert submitted == text
        assert timeout == 10
        return "0.88\tAda Lovelace\tworks for\tAnalytical Engines Ltd.\n"
    extractor = StanfordOpenIEExtractor(
        command=("java", "-cp", "stanford-corenlp/*", "edu.stanford.nlp.naturalli.OpenIE"),
        runner=runner, timeout_seconds=10,
    )
    report = extractor.report(text, scope=_scope())
    assert len(report.signals) == 1
    assert report.refusals == ()
    assert report.signals[0].producer_ref == "openie/stanford-corenlp"
    assert report.signals[0].relation_surface == "works for"
    assert report.signals[0].producer_confidence == 0.88
    assert len(stanford_openie_signals([text], scope=_scope(), extractor=extractor)) == 1
    assert extractor.declares().independence_family == "relation-ml-producers"



def test_stanford_openie_refuses_repeated_participant_occurrences():
    text = "Ada Lovelace works for Analytical Engines. Ada Lovelace works for Analytical Engines."
    extractor = StanfordOpenIEExtractor(
        runner=lambda *_: "0.9\tAda Lovelace\tworks for\tAnalytical Engines.\n"
    )
    report = extractor.report(text, scope=_scope())
    assert report.signals == ()
    assert report.refusals[0].code == "tuple_occurrences_ambiguous"

def test_stanford_openie_never_promotes_unanchored_tuple():
    text = "Ada Lovelace joined Analytical Engines Ltd."
    extractor = StanfordOpenIEExtractor(
        runner=lambda *_: "0.9\tAda Lovelace\tworks for\tAnalytical Engines Ltd.\n"
    )
    report = extractor.report(text, scope=_scope())
    assert report.signals == ()
    assert report.refusals[0].code == "tuple_not_source_grounded"
