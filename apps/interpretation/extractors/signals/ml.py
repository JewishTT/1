"""Optional ML / OpenIE relation producers adapted to the canonical RelationSignal contract.

No producer creates mentions, entities, candidates, claims or graph edges. A model relation
label is never passed off as source text: a signal is emitted only when the predicate can be
located between the exact participant spans. Un-groundable predictions become typed refusals.
The module has no mandatory ML dependency; GLiNER is loaded lazily.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from domain.predicate_signature import ArgumentSlot
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals.mentions import deferred_occurrence
from extractors.signals.protocol import ExtractionScope, ProducerDeclaration, run_producer
from extractors.signals.signal import DirectionHypothesis, Neighbourhood, RelationSignal, SignalKind

GLINER_PRODUCER_REF = "ml/gliner-relex"
GLINER_PRODUCER_VERSION = "1"
OPENIE_PRODUCER_REF = "openie/stanford-corenlp"
OPENIE_PRODUCER_VERSION = "1"
# Two extractors over one capture are not two independent evidence sources.
RELATION_ML_INDEPENDENCE_FAMILY = "relation-ml-producers"
MAX_DOCUMENT_CHARS = 12_000
MAX_RELATION_PAIRS = 1_024


@dataclass(frozen=True, slots=True)
class ExtractionRefusal:
    code: str
    producer_ref: str
    detail: str
    record_ordinal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "producer_ref": self.producer_ref,
                "detail": self.detail, "record_ordinal": self.record_ordinal}


@dataclass(frozen=True, slots=True)
class RelationProducerReport:
    signals: tuple[RelationSignal, ...]
    refusals: tuple[ExtractionRefusal, ...]
    producer_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals))
        object.__setattr__(self, "refusals", tuple(self.refusals))

    def counts(self) -> dict[str, int]:
        return {"signals": len(self.signals), "refusals": len(self.refusals)}


def _text_and_overrides(record: object) -> tuple[str, Mapping[str, str]]:
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        body = str(record.get("text") or record.get("markdown") or record.get("content") or "")
        overrides = {key: str(record[key]) for key in
                     ("context_ref", "semantic_regime_ref", "document_ref", "language")
                     if record.get(key)}
        return body, overrides
    return "", {}


def _normalise_phrase(value: str) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def _phrase_span(text: str, phrase: str, start: int, end: int) -> tuple[int, int, str] | None:
    if start < 0 or end < start or end > len(text):
        return None
    expected = _normalise_phrase(phrase)
    if not expected:
        return None
    region = text[start:end]
    pattern = re.compile(r"\s+".join(re.escape(token) for token in expected.split()),
                         flags=re.IGNORECASE)
    matches = list(pattern.finditer(region))
    # More than one trigger in this inter-argument region is not a reason to take
    # the first: it is an ambiguous source locator and must be refused.
    if len(matches) != 1:
        return None
    match = matches[0]
    left, right = start + match.start(), start + match.end()
    return left, right, text[left:right]


def _entity_span(text: str, entity: Mapping[str, Any]) -> tuple[int, int, str] | None:
    try:
        start, end = int(entity["start"]), int(entity["end"])
    except (KeyError, TypeError, ValueError):
        return None
    surface = str(entity.get("text") or "")
    if start < 0 or end <= start or end > len(text) or text[start:end] != surface:
        return None
    return start, end, surface


def _signal(
    *, text: str, subject: Mapping[str, Any], object_: Mapping[str, Any],
    predicate: str, score: float, producer_ref: str, producer_version: str,
    ordinal: int, scope: ExtractionScope, model_ref: str,
) -> RelationSignal | None:
    subject_span, object_span = _entity_span(text, subject), _entity_span(text, object_)
    if subject_span is None or object_span is None:
        return None
    s_start, s_end, s_surface = subject_span
    o_start, o_end, o_surface = object_span
    if s_start < o_end and o_start < s_end:
        return None
    between_start, between_end = (s_end, o_start) if s_end <= o_start else (o_end, s_start)
    predicate_span = _phrase_span(text, predicate, between_start, between_end)
    if predicate_span is None or not 0.0 <= float(score) <= 1.0:
        return None
    p_start, p_end, source_predicate = predicate_span

    return RelationSignal(
        participants=(
            RelationParticipant(
                mention_ref=deferred_occurrence(label="A0", surface=s_surface,
                                                start=s_start, end=s_end),
                slot=ArgumentSlot(0), role_hypothesis=str(subject.get("label") or "A0"),
                ordinal=0, confidence=float(subject.get("score", 0.0) or 0.0),
            ),
            RelationParticipant(
                mention_ref=deferred_occurrence(label="A1", surface=o_surface,
                                                start=o_start, end=o_end),
                slot=ArgumentSlot(1), role_hypothesis=str(object_.get("label") or "A1"),
                ordinal=1, confidence=float(object_.get("score", 0.0) or 0.0),
            ),
        ),
        kind=SignalKind.SEMANTIC,
        relation_surface=source_predicate,
        basis=SignalBasis.PREDICATE_TEXT,
        direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
        neighbourhood=Neighbourhood(
            characters_scanned=len(text), pairs_considered=1,
            scope_read=(f"one model-returned directed pair in {len(text)} source characters; "
                        "argument and predicate surfaces verified against original text"),
            precision="exact",
            notes=f"model={model_ref}; predicate span=[{p_start},{p_end})",
        ),
        producer_confidence=float(score), signal_ordinal=ordinal,
        tenant_id=scope.tenant_id, context_ref=scope.context_ref,
        semantic_regime_ref=scope.semantic_regime_ref, capture_ref=scope.document_ref,
        producer_ref=producer_ref, producer_version=producer_version,
        extra={"model_ref": model_ref, "model_predicate_label": str(predicate),
               "source_predicate_span": [p_start, p_end],
               "subject_span": [s_start, s_end], "object_span": [o_start, o_end],
               "subject_label": str(subject.get("label") or ""),
               "object_label": str(object_.get("label") or "")},
    )


def _relation_entries(entities: Sequence[Mapping[str, Any]],
                      relations: Sequence[Mapping[str, Any]]) -> list[tuple[Mapping[str, Any], Mapping[str, Any], str, float]]:
    found = []
    for relation in relations:
        head, tail = relation.get("head") or {}, relation.get("tail") or {}
        try:
            subject, object_ = entities[int(head.get("entity_idx", -1))], entities[int(tail.get("entity_idx", -1))]
            score = float(relation.get("score", 0.0))
        except (IndexError, TypeError, ValueError):
            continue
        predicate = str(relation.get("relation") or "").strip()
        if predicate:
            found.append((subject, object_, predicate, score))
    return found


def _scoped(scope: ExtractionScope, overrides: Mapping[str, str]) -> ExtractionScope:
    return ExtractionScope(
        tenant_id=scope.tenant_id,
        context_ref=overrides.get("context_ref") or scope.context_ref,
        semantic_regime_ref=overrides.get("semantic_regime_ref") or scope.semantic_regime_ref,
        document_ref=overrides.get("document_ref") or scope.document_ref,
        investigation_id=scope.investigation_id, recorded_by=scope.recorded_by,
        labels=scope.labels,
    )


class GLiNERRelexExtractor:
    """Joint GLiNER entity/relation producer with fail-closed source grounding."""

    def __init__(
        self, model: Any, *, model_ref: str = "knowledgator/gliner-relex-large-v1.0",
        entity_labels: Sequence[str] = ("person", "organization", "role", "date", "location"),
        relation_labels: Sequence[str] = ("works for", "founded", "holds role at",
                                           "member of", "authored", "affiliated with"),
        entity_threshold: float = 0.5, relation_threshold: float = 0.65,
        max_document_chars: int = MAX_DOCUMENT_CHARS,
        max_pairs_considered: int = MAX_RELATION_PAIRS,
    ) -> None:
        if model is None:
            raise ValueError("a loaded GLiNER RelEx model is required")
        self.model, self.model_ref = model, str(model_ref)
        self.entity_labels, self.relation_labels = tuple(entity_labels), tuple(relation_labels)
        self.entity_threshold, self.relation_threshold = float(entity_threshold), float(relation_threshold)
        self.max_document_chars, self.max_pairs_considered = int(max_document_chars), int(max_pairs_considered)
        if not self.entity_labels or not self.relation_labels:
            raise ValueError("GLiNER entity_labels and relation_labels must be non-empty")
        if not 0 <= self.entity_threshold <= 1 or not 0 <= self.relation_threshold <= 1:
            raise ValueError("GLiNER thresholds must be in [0, 1]")
        if self.max_document_chars < 1 or self.max_pairs_considered < 1:
            raise ValueError("GLiNER extraction bounds must be positive")

    @classmethod
    def from_pretrained(cls, model_ref: str = "knowledgator/gliner-relex-large-v1.0",
                        **kwargs: Any) -> GLiNERRelexExtractor:
        try:
            from gliner import GLiNER
        except ImportError as exc:
            raise RuntimeError(
                "GLiNER is optional; install the upstream gliner package in the runtime image to enable it"
            ) from exc
        return cls(GLiNER.from_pretrained(model_ref), model_ref=model_ref, **kwargs)

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=GLINER_PRODUCER_REF, producer_version=GLINER_PRODUCER_VERSION,
            kinds=(SignalKind.SEMANTIC,),
            reads=("bounded text; jointly predicts entity spans and relation labels; emits "
                   "only predicates that can be located verbatim between exact participant spans"),
            cannot_read=("truth, identity, source independence, role validity or temporal validity. "
                         "A predicted label not grounded as a source span is refused, never quoted"),
            max_pairs_considered=self.max_pairs_considered, independence_family=RELATION_ML_INDEPENDENCE_FAMILY,
            notes=f"checkpoint={self.model_ref}; explicit thresholds; no claim or graph writes",
        )

    def report(self, record: object, *, scope: ExtractionScope) -> RelationProducerReport:
        text, overrides = _text_and_overrides(record)
        if not text.strip():
            return RelationProducerReport((), (), GLINER_PRODUCER_REF)
        if len(text) > self.max_document_chars:
            return RelationProducerReport((), (ExtractionRefusal(
                "document_exceeds_character_ceiling", GLINER_PRODUCER_REF,
                f"{len(text)} characters exceed limit {self.max_document_chars}"),), GLINER_PRODUCER_REF)
        output = self.model.inference(
            [text], labels=list(self.entity_labels), relations=list(self.relation_labels),
            threshold=self.entity_threshold, relation_threshold=self.relation_threshold,
        )
        if not isinstance(output, (tuple, list)) or len(output) != 2:
            return RelationProducerReport((), (ExtractionRefusal(
                "model_output_shape_invalid", GLINER_PRODUCER_REF,
                "expected (entities, relations)"),), GLINER_PRODUCER_REF)
        try:
            entities, relations = list(output[0][0]), list(output[1][0])
        except (IndexError, TypeError):
            return RelationProducerReport((), (ExtractionRefusal(
                "model_batch_shape_invalid", GLINER_PRODUCER_REF,
                "single-document batch is missing"),), GLINER_PRODUCER_REF)
        pair_count = len(entities) * (len(entities) - 1) // 2
        if pair_count > self.max_pairs_considered:
            return RelationProducerReport((), (ExtractionRefusal(
                "relation_pair_ceiling_exceeded", GLINER_PRODUCER_REF,
                f"{len(entities)} entities imply {pair_count} pairs; limit is {self.max_pairs_considered}"),),
                GLINER_PRODUCER_REF)
        source_scope = _scoped(scope, overrides)
        signals, refusals = [], []
        for ordinal, (subject, object_, predicate, score) in enumerate(_relation_entries(entities, relations)):
            signal = _signal(
                text=text, subject=subject, object_=object_, predicate=predicate, score=score,
                producer_ref=GLINER_PRODUCER_REF, producer_version=GLINER_PRODUCER_VERSION,
                ordinal=ordinal, scope=source_scope, model_ref=self.model_ref,
            )
            if signal is None:
                refusals.append(ExtractionRefusal(
                    "prediction_not_source_grounded", GLINER_PRODUCER_REF,
                    f"relation={predicate!r}; participants or predicate do not map to exact source spans",
                    ordinal))
            else:
                signals.append(signal)
        return RelationProducerReport(tuple(signals), tuple(refusals), GLINER_PRODUCER_REF)

    def extract(self, record: object, *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
        return self.report(record, scope=scope).signals


class StanfordOpenIEExtractor:
    """Stanford OpenIE producer using an explicit, bounded Java CLI argv."""

    def __init__(
        self, command: Sequence[str] = ("java", "-mx1g", "-cp", "*",
                                        "edu.stanford.nlp.naturalli.OpenIE"),
        *, runner: Callable[[Sequence[str], str, float], str] | None = None,
        version: str = "stanford-corenlp-openie-configured", timeout_seconds: float = 45.0,
        max_document_chars: int = MAX_DOCUMENT_CHARS,
        max_pairs_considered: int = MAX_RELATION_PAIRS,
    ) -> None:
        self.command, self.runner = tuple(str(v) for v in command), runner or self._run_java
        self.version, self.timeout_seconds = str(version), float(timeout_seconds)
        self.max_document_chars, self.max_pairs_considered = int(max_document_chars), int(max_pairs_considered)
        if not self.command or any(not item.strip() for item in self.command):
            raise ValueError("Stanford OpenIE command must be an explicit non-empty argv")
        if self.timeout_seconds <= 0 or self.max_document_chars < 1 or self.max_pairs_considered < 1:
            raise ValueError("Stanford OpenIE timeout and bounds must be positive")

    @staticmethod
    def _run_java(command: Sequence[str], text: str, timeout: float) -> str:
        completed = subprocess.run(list(command), input=text, text=True,
                                   capture_output=True, check=False, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError(f"Stanford OpenIE exited {completed.returncode}: {completed.stderr[-1000:]}")
        return completed.stdout

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=OPENIE_PRODUCER_REF, producer_version=OPENIE_PRODUCER_VERSION,
            kinds=(SignalKind.SEMANTIC,),
            reads=("source text submitted to Stanford OpenIE; open-domain subject/predicate/object "
                   "tuples are aligned against literal source spans"),
            cannot_read=("truth, person identity, source independence, role validity or temporal "
                         "validity; any tuple not grounded in the original text is refused"),
            max_pairs_considered=self.max_pairs_considered, independence_family=RELATION_ML_INDEPENDENCE_FAMILY,
            notes=f"version={self.version}; subprocess argv only, no shell; timeout and input bounds",
        )

    @staticmethod
    def _parse_rows(output: str) -> list[tuple[float, str, str, str]]:
        rows = []
        for line in str(output or "").splitlines():
            fields = line.split("\t")
            if len(fields) != 4:
                continue
            try:
                confidence = float(fields[0].strip())
            except ValueError:
                continue
            subject, predicate, object_ = (field.strip() for field in fields[1:])
            if subject and predicate and object_ and 0 <= confidence <= 1:
                rows.append((confidence, subject, predicate, object_))
        return rows

    @staticmethod
    def _occurrences(text: str, surface: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in re.finditer(re.escape(surface), text, re.IGNORECASE)] if surface else []

    def report(self, record: object, *, scope: ExtractionScope) -> RelationProducerReport:
        text, overrides = _text_and_overrides(record)
        if not text.strip():
            return RelationProducerReport((), (), OPENIE_PRODUCER_REF)
        if len(text) > self.max_document_chars:
            return RelationProducerReport((), (ExtractionRefusal(
                "document_exceeds_character_ceiling", OPENIE_PRODUCER_REF,
                f"{len(text)} characters exceed limit {self.max_document_chars}"),), OPENIE_PRODUCER_REF)
        try:
            output = self.runner(self.command, text, self.timeout_seconds)
        except subprocess.TimeoutExpired:
            return RelationProducerReport((), (ExtractionRefusal(
                "openie_timeout", OPENIE_PRODUCER_REF, "Java process exceeded its timeout"),), OPENIE_PRODUCER_REF)
        rows = self._parse_rows(output)
        if len(rows) > self.max_pairs_considered:
            return RelationProducerReport((), (ExtractionRefusal(
                "relation_pair_ceiling_exceeded", OPENIE_PRODUCER_REF,
                f"{len(rows)} triples exceed limit {self.max_pairs_considered}"),), OPENIE_PRODUCER_REF)
        source_scope = _scoped(scope, overrides)
        signals, refusals = [], []
        for ordinal, (confidence, subject_text, predicate, object_text) in enumerate(rows):
            subjects, objects = self._occurrences(text, subject_text), self._occurrences(text, object_text)
            choices = [(s_start, s_end, o_start, o_end)
                       for s_start, s_end in subjects for o_start, o_end in objects
                       if s_end <= o_start or o_end <= s_start]
            signal = None
            if len(subjects) == 1 and len(objects) == 1 and len(choices) == 1:
                s_start, s_end, o_start, o_end = choices[0]
                subject = {"start": s_start, "end": s_end, "text": text[s_start:s_end], "label": "subject"}
                object_ = {"start": o_start, "end": o_end, "text": text[o_start:o_end], "label": "object"}
                signal = _signal(
                    text=text, subject=subject, object_=object_, predicate=predicate,
                    score=confidence, producer_ref=OPENIE_PRODUCER_REF,
                    producer_version=OPENIE_PRODUCER_VERSION, ordinal=ordinal,
                    scope=source_scope, model_ref=self.version,
                )
            if signal is None:
                code = (
                    "tuple_occurrences_ambiguous"
                    if len(subjects) > 1 or len(objects) > 1
                    else "tuple_not_source_grounded"
                )
                refusals.append(ExtractionRefusal(
                    code, OPENIE_PRODUCER_REF,
                    f"subject={subject_text!r}; predicate={predicate!r}; object={object_text!r}",
                    ordinal,
                ))
            else:
                signals.append(signal)
        return RelationProducerReport(tuple(signals), tuple(refusals), OPENIE_PRODUCER_REF)

    def extract(self, record: object, *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
        return self.report(record, scope=scope).signals


def gliner_relex_signals(records: Sequence[object], *, scope: ExtractionScope,
                         extractor: GLiNERRelexExtractor) -> tuple[RelationSignal, ...]:
    return run_producer(extractor, records, scope=scope)


def stanford_openie_signals(records: Sequence[object], *, scope: ExtractionScope,
                             extractor: StanfordOpenIEExtractor) -> tuple[RelationSignal, ...]:
    return run_producer(extractor, records, scope=scope)


__all__ = [
    "ExtractionRefusal", "GLiNERRelexExtractor", "MAX_DOCUMENT_CHARS",
    "MAX_RELATION_PAIRS", "OPENIE_PRODUCER_REF", "OPENIE_PRODUCER_VERSION",
    "RelationProducerReport", "StanfordOpenIEExtractor", "gliner_relex_signals",
    "stanford_openie_signals",
]
