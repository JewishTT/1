"""Functional smoke for extractors.relations (spec 018 T021-T023, FR-017..FR-019).

Run from the repo root:
    uv run --project apps/interpretation python tmp/smoke_relations.py
"""

from __future__ import annotations

import inspect

import extractors.relations as rel
from domain.relation_candidate import CandidateStatus, RelationCandidate
from domain.relation_schema import RelationSchema
from extractors.registry import DeterministicExtractorSet
from extractors.util import byte_offset
from semantic.blocking import RelationRole, affordance_kinds
from semantic.operators import default_operator_for_schema

GOLDEN = "John Smith became CEO of Acme in 2020."
CUE = "CEO of"


def head(title: str) -> None:
    print()
    print(f"== {title}")


def b(text: str, index: int) -> int:
    return byte_offset(text, index)


# (a) two mentions, organisation reached through the cue, no legal-form suffix ------
head("(a) mentions: Acme has no legal form and is still an organisation")
extractors = DeterministicExtractorSet()
extractors.register_builtin()
print("baseline (five built-ins only), no cue rule registered:")
for m in extractors.extract(GOLDEN, segment_ref="seg-1"):
    print(f"   {m.kind:<7} {m.value!r:<14} [{m.offset},{m.end_offset}) {m.extractor}")
rel.register_relational_extractors(extractors)
print("after register_relational_extractors(); names:", extractors.names())
mentions = extractors.extract(GOLDEN, segment_ref="seg-1")
for m in mentions:
    print(f"   {m.kind:<7} {m.value!r:<14} [{m.offset},{m.end_offset}) {m.extractor} {m.source}")
print("   count =", len(mentions))
acme = [m for m in mentions if m.value == "Acme"]
print("   'Acme' mentions:", [(m.kind, m.extractor, m.evidence.get("cue")) for m in acme])
orgs_grammar = __import__("extractors.orgs", fromlist=["x"]).extract_organizations(GOLDEN)
print("   extractors.orgs alone finds:", [m.value for m in orgs_grammar])
print("   moving rule extract_role_target_orgs ->", [m.to_dict() for m in
      rel.extract_role_target_orgs(GOLDEN)])

# (b) the relational reading -------------------------------------------------------
head("(b) relational reading")
sites = rel.extract_cue_sites(GOLDEN)
for site in sites:
    print(f"   site cue_id={site.cue_id} role={site.role_surface!r} "
          f"object={site.object_surface!r} trigger={site.trigger_surface!r}")
readings = rel.extract_relational_readings(GOLDEN, lang_hint="en", observation_refs=("obs-1",))
for r in readings:
    print(f"   reading cue_id={r.cue_id} relation_ref={r.relation_ref} "
          f"method={r.extraction_method} version={r.extractor_version} rule={r.extraction_rule_id}")
    print(f"     trigger_span   [{r.trigger_span.start},{r.trigger_span.end}) "
          f"{r.trigger_span.surface!r}")
    print(f"     subject        {r.subject.mention.kind} {r.subject.mention.value!r} "
          f"role={r.subject.role} ref={r.subject.mention_ref}")
    print(f"     object         {r.object.mention.kind} {r.object.mention.value!r} "
          f"role={r.object.role} ref={r.object.mention_ref}")
    print(f"     role_assignment {r.role_assignment!r}")
    print(f"     role_bindings  {[(x.role, x.member_ref, x.member_class) for x in r.role_bindings()]}")
    for s in r.supporting_spans:
        print(f"     supporting     [{s.start},{s.end}) {s.surface!r} mention_ref={s.mention_ref!r}")
    print(f"     temporal       {r.temporal_hypothesis.to_dict()}")
    print(f"     arity_mode     {r.arity_mode}")

r = readings[0]
assert r.trigger_span.surface == CUE, r.trigger_span.surface
assert GOLDEN.encode()[r.trigger_span.start:r.trigger_span.end].decode() == CUE
print("   trigger covers 'CEO of':",
      GOLDEN.encode()[r.trigger_span.start:r.trigger_span.end].decode() == CUE)

# (c) affordance vocabulary lines up with blocking --------------------------------
head("(c) affordance vocabulary vs semantic.blocking / semantic.operators")
aff = rel.cue_affordance("CEO")
print("   cue_affordance('CEO') =", aff)
print("   declared subject_kinds", aff.subject_kinds, "object_kinds", aff.object_kinds)
print("   kinds_for(OBJECT)     ", aff.kinds_for(RelationRole.OBJECT))
print("   kinds_for(SUBJECT)    ", aff.kinds_for(RelationRole.SUBJECT))
print("   mention_kind_for(OBJ) ", aff.mention_kind_for(RelationRole.OBJECT))
print("   type_hypotheses(OBJ)  ", [h.reference() for h in aff.type_hypotheses(RelationRole.OBJECT)])
schema = RelationSchema(
    relation_type="works_for",
    arity_mode=rel.RelationArityMode.NARY,
    allowed_subject_classes=frozenset({"schema:Person"}),
    allowed_object_classes=frozenset({"schema:Organization"}),
    allowed_role_classes={
        "organization": frozenset({"schema:Organization"}),
        "person": frozenset({"schema:Person"}),
    },
    admissible_evidence_patterns=("context", "relation_pattern"),
    temporal_semantics=rel.TemporalSemantics.POINT,
)
operator = default_operator_for_schema(schema)
blocking_object = affordance_kinds(operator, RelationRole.OBJECT)
blocking_subject = affordance_kinds(operator, RelationRole.SUBJECT)
print("   affordance_kinds(operator, OBJECT) =", blocking_object)
print("   affordance_kinds(operator, SUBJECT)=", blocking_subject)
print("   operator.object_kinds =", operator.object_kinds, " subject_kinds =", operator.subject_kinds)
print("   cue kinds == operator kinds:",
      aff.kinds_for(RelationRole.OBJECT) == blocking_object
      and aff.kinds_for(RelationRole.SUBJECT) == blocking_subject)
print("   matches_operator(cue, operator) =", rel.matches_operator(aff, operator))
print("   the affordance IS the affordance blocking reads:",
      affordance_kinds(aff, RelationRole.OBJECT) == blocking_object)

# (d) an absent temporal hypothesis is representable and raises nothing ------------
head("(d) absent temporal hypothesis")
no_date = "John Smith became CEO of Acme."
rd = rel.extract_relational_readings(no_date)
print("   ", no_date, "->", len(rd), "reading(s)")
print("   temporal:", rd[0].temporal_hypothesis.to_dict())
print("   carries_window():", rd[0].temporal_hypothesis.carries_window(),
      " basis:", rd[0].temporal_hypothesis.basis)
print("   TemporalHypothesis.absent() ->",
      rel.TemporalHypothesis.absent().to_dict())
print("   absent() x3 equal:", rel.TemporalHypothesis.absent() == rel.TemporalHypothesis.absent())

# (e) PROPOSE, and no API to set any other status ---------------------------------
head("(e) the reading is PROPOSE and the module cannot say anything else")
cand = r.to_candidate(
    segment_ref="seg-1",
    context_ref="ctx-1",
    semantic_regime_ref="regime-1",
    mention_refs={"subject": "MN-subject", "object": "MN-object"},
)
print("   candidate_status =", cand.candidate_status, " is_admissible =", cand.is_admissible)
print("   trigger_span     =", cand.trigger_span.to_dict())
print("   supporting_spans =", [s.to_dict() for s in cand.supporting_spans])
print("   role_assignments =", [x.to_dict() for x in cand.role_assignments])
print("   relation_ref     =", str(cand.relation_ref), cand.relation_type, cand.schema_version)
print("   extraction_method=", cand.extraction_method, " extractor_version =", cand.extractor_version)
print("   temporal         =", cand.temporal_hypothesis.to_dict())
print("   evidence_refs    =", list(cand.evidence_refs))
print("   with_id()        =", cand.with_id().candidate_id, cand.with_id().logical_candidate_id)

public = [n for n in dir(rel) if not n.startswith("_")]
print("   module public names:", public)
print("   'CandidateStatus' reachable on the module?",
      hasattr(rel, "CandidateStatus"))


def own_callables(obj: object, label: str) -> list[tuple[str, object]]:
    found = []
    for name, member in vars(obj).items():
        target = getattr(obj, name, None)
        if not callable(target) or getattr(target, "__module__", "") != rel.__name__:
            continue
        if inspect.isclass(obj) and name.startswith("_"):
            continue
        found.append((f"{label}.{name}" if label else name, target))
    return found


def status_params(name: str, fn: object) -> list[str]:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return []
    return [p for p in ("candidate_status", "status", "disposition") if p in params]


surfaces = own_callables(rel, "")
for cls in (rel.RelationalReading, rel.CueParticipant, rel.CueAffordance, rel.RelationCue,
            rel.CueSite, rel.CueSpan):
    surfaces += own_callables(cls, cls.__name__)
bad_status = [f"{name}{status_params(name, fn)}" for name, fn in surfaces if status_params(name, fn)]
print("   own callables inspected:", [n for n, _ in surfaces])
print("   anything status-shaped on the public surface:", bad_status)
print("   dataclass fields mentioning a status:",
      [f"{c.__name__}.{f.name}" for c in (rel.RelationalReading, rel.CueParticipant,
        rel.CueAffordance, rel.RelationCue, rel.CueSite, rel.CueSpan)
       for f in c.__dataclass_fields__.values() if "status" in f.name or "disposition" in f.name])
print("   every produced candidate status:",
      {c.candidate_status for c in [r.to_candidate(segment_ref="s", context_ref="c",
                                                  semantic_regime_ref="g")]})
print("   'CandidateStatus' in the raw source (docstrings only):",
      "CandidateStatus" in inspect.getsource(rel))
import ast

tree = ast.parse(inspect.getsource(rel))
name_hits = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "CandidateStatus"]
attr_hits = [f"{n.value.id}.{n.attr}" for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
             and n.value.id == "CandidateStatus"]
imports = [a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
           for a in n.names]
print("   AST Name nodes 'CandidateStatus':", name_hits,
      "| Attribute accesses:", attr_hits)
print("   AST imports from domain.relation_candidate:", [a for n in ast.walk(tree)
      if isinstance(n, ast.ImportFrom) and n.module == "domain.relation_candidate"
      for a in n.names])
print("   RelationCandidate default status:", RelationCandidate.__dataclass_fields__
      ["candidate_status"].default)
print("   SUPPORTED reachable from this module at all?",
      hasattr(rel, "SUPPORTED"),
      "| any attr value equal to CandidateStatus.SUPPORTED:",
      any(v == CandidateStatus.SUPPORTED for v in vars(rel).values()))

# (f) determinism ------------------------------------------------------------------
head("(f) determinism: two runs, identical spans and values")
def run() -> tuple:
    ms = extractors.extract(GOLDEN, segment_ref="seg-1")
    rs = rel.extract_relational_readings(GOLDEN, lang_hint="en", observation_refs=("obs-1",))
    return (
        [(m.kind, m.value, m.offset, m.end_offset, m.extractor, m.confidence) for m in ms],
        [x.identity for x in rs[0].supporting_spans],
        rs[0].to_candidate(segment_ref="seg-1", context_ref="ctx-1",
                           semantic_regime_ref="regime-1").with_id().candidate_id,
        str(rs[0].relation_ref),
        rs[0].temporal_hypothesis.to_dict(),
    )
a, bb = run(), run()
for label, left, right in zip(
    ("mentions", "supporting_spans", "candidate_id", "relation_ref", "temporal"), a, bb
):
    print(f"   {label:<18} identical = {left == right}  {left}")

# (g) no cue -> plain mentions, no reading, no error --------------------------------
head("(g) a sentence with no relation cue")
plain = "John Smith visited Kazan in 2020."
print("   ", repr(plain))
print("   cue sites        :", rel.extract_cue_sites(plain))
print("   relational reads :", rel.extract_relational_readings(plain))
print("   affordance       :", rel.cue_affordance(plain), rel.cue_affordance("banana"))
print("   role_target_orgs :", rel.extract_role_target_orgs(plain))
plain_mentions = []
set2 = DeterministicExtractorSet()
set2.register_builtin()
rel.register_relational_extractors(set2)
for m in set2.extract(plain, segment_ref="seg-1"):
    plain_mentions.append((m.kind, m.value, m.extractor))
    print(f"   {m.kind:<7} {m.value!r:<14} {m.extractor}")
print("   empty text       :", rel.extract_cue_sites(""), rel.extract_relational_readings(""),
      rel.extract_relational_mentions(""), rel.extract_role_target_orgs(""))

# bonus: the second cue row (ru), and what the cue still adds beside orgs ----------
head("bonus: the second cue row (ru), and 'CEO of Acme Corporation'")
ru = "Иван Петров был директором Ромашка в 2019."
print("   ", ru)
for rr in rel.extract_relational_readings(ru, lang_hint="ru"):
    print(f"   {rr.cue_id} trigger={rr.trigger_span.surface!r} "
          f"subject={rr.subject.mention.value!r} object={rr.object.mention.value!r} "
          f"role={rr.role_assignment!r} t={rr.temporal_hypothesis.to_dict()['valid_from']}")
print("   a ru sentence with no role word is not a cue:",
      rel.extract_cue_sites("Иван Петров работал в Ромашка."))
suffixed = "John Smith became CEO of Acme Corporation in 2020."
print("   ", suffixed)
s3 = DeterministicExtractorSet()
s3.register_builtin()
rel.register_relational_extractors(s3)
print("   fan-out :", [(m.kind, m.value, m.extractor) for m in
                       s3.extract(suffixed, segment_ref="seg-1")])
print("   reading :", rel.extract_relational_readings(suffixed)[0].object.mention.value,
      "(extractors.orgs swallows the cue; the reading does not - pre-existing, orgs.py"
      " is untouched)")
print()
print("SMOKE OK")
