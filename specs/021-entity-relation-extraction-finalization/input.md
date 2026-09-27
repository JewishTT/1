# FEATURE 021 — FINALIZE ENTITY / RELATION EXTRACTION SUBSTRATE

> **Verbatim source of truth.** This file is the user's Feature 021 brief, reproduced
> **without reduction, abridgement or paraphrase**. It is the input `speckit.specify` was
> invoked with and the authority for every requirement in `spec.md`. Where `spec.md`
> appears to summarise something, this file governs.
>
> Captured at HEAD `00566655828258485795d58d38b5ebcdafb5ee9a`, previous constitutional
> point `81d810795ab1cf24e03931cb7ccc40915c6f296d`.

---

## 0. Режим работы

Работай **не как генератор локальных патчей**, а как архитектор репозитория.

Репозиторий:

`https://github.com/JewishTT/1`

Текущий HEAD на начало задачи:

`00566655828258485795d58d38b5ebcdafb5ee9a`

Предыдущая конституционально значимая точка:

`81d810795ab1cf24e03931cb7ccc40915c6f296d`

Текущий Feature 019 уже реализовал большую часть substrate:

* `RelationSignal`
* `RelationSignalExtractor`
* signal producers
* `RelationCandidate`
* `PredicateHypothesis`
* `RelationCandidate` persistence schema
* `SourceTemporalObservation`
* signal assembly
* базовую universal relation extraction architecture
* bounded neighbourhood
* open-world predicate semantics
* distinction mention/entity
* claim/material separation
* forward-only migration 020

Но **не считай отчёт предыдущего агента доказательством корректности**.

Перед внесением изменений:

1. Проверь настоящий HEAD.
2. Прочитай:

   * `specs/019-universal-relation-extraction/spec.md`
   * `specs/019-universal-relation-extraction/plan.md`
   * `specs/019-universal-relation-extraction/tasks.md`
   * `.specify/memory/constitution.md`
3. Прочитай:

   * `apps/shared/domain/relation_candidate.py`
   * `apps/shared/domain/predicate_hypothesis.py`
   * `apps/shared/domain/relation_claim_material.py`
   * `apps/shared/domain/relation_claim.py`
   * `apps/shared/domain/relation_identity.py`
   * `apps/shared/domain/temporal_observation.py`
   * `apps/shared/domain/evidence_lineage.py`
   * `apps/shared/semantic/contracts.py`
   * `apps/shared/semantic/blocking.py`
   * `apps/shared/semantic/operators.py`
   * `apps/shared/semantic/registry.py`
   * `apps/shared/semantic/vocabularies.py`
   * `apps/shared/semantic/regime.py`
   * `apps/shared/semantic/resolution.py`
   * `apps/interpretation/extractors/registry.py`
   * `apps/interpretation/extractors/types.py`
   * `apps/interpretation/extractors/persons.py`
   * `apps/interpretation/extractors/orgs.py`
   * `apps/interpretation/extractors/places.py`
   * `apps/interpretation/extractors/contacts.py`
   * `apps/interpretation/extractors/dictionary_entities.py`
   * `apps/interpretation/extractors/relations.py`
   * `apps/interpretation/extractors/signals/*`
   * `apps/control-plane/semantic_path/*`
   * `apps/control-plane/db/schema.py`
   * `apps/control-plane/db/migrations/versions/019_world_substrate.py`
   * `apps/control-plane/db/migrations/versions/020_universal_relation_extraction.py`
   * `apps/projection/graph/*`
     3.4. Search all call sites of:
   * `RelationCandidate`
   * `RelationSignal`
   * `CandidateStatus`
   * `relation_surface`
   * `relation_ref`
   * `GraphEdge`
   * `HyperEdge`
   * `TypeAssertion`
   * `TypeHypothesis`
   * `OntologyPack`
4. Only after understanding the actual repository, create/update the Feature 021 specification.

Do not blindly preserve an existing abstraction if the abstraction contradicts the platform constitution.

---

# 1. MISSION

Complete the extraction/interpretation layer so that the platform has a coherent end-to-end substrate for:

```text
raw observation
→ contextualized observation
→ mentions
→ atomic semantic type hypotheses
→ entity type assertions
→ relational observations
→ relational hypotheses/candidates
→ entity resolution
→ predicate interpretation
→ validated claim material
→ admitted RelationClaim
→ GraphEdge / HyperEdge projection
→ Worldline
```

The completed architecture must support two fundamentally different things:

### A. Entity interpretation

The platform may use a **substantial foundational vocabulary of atomic entity/resource types**.

Examples:

```text
Person
Organization
LegalEntity
Group
WebSite
WebPage
OnlineAccount
SocialProfile
Domain
PhysicalPlace
Facility
Address
Country
Region
City
Document
Dataset
Software
Product
Service
Event
CreativeWork
MediaResource
Vehicle
FinancialInstrument
Asset
Project
```

plus value/data types:

```text
EmailAddress
PhoneNumber
URL
Handle
Identifier
IPAddress
Hash
CryptoAddress
Date
DateTime
Money
Quantity
Coordinate
```

This is allowed and desired.

### B. Relation interpretation

Do **NOT** construct an equivalent huge mandatory ontology of every possible edge type.

There should be no requirement like:

```text
every relation must be one of:
works_for
owns
controls
founded
located_in
...
```

before the platform is allowed to preserve it.

The relation substrate must remain open-world.

This distinction is constitutional:

```text
TYPE SPACE:
bounded, versioned, extensible foundational vocabulary

RELATION SPACE:
open, observable, hypothesis-driven, optionally mapped into known operators
```

This is the vector.

---

# 2. CORE ARCHITECTURAL DECISION

Do not return to an ontology-first architecture.

The ontology/type vocabulary is an **interpretation instrument**.

It is:

* a naming system,
* a hierarchy,
* a source of aliases,
* a blocking accelerator,
* a role/domain/range hint,
* a mapping surface,
* a validation vocabulary.

It is NOT:

* the definition of what exists,
* a permit/deny gate,
* a completeness condition,
* the source of truth,
* a mandatory relation universe.

SKOS is appropriate as inspiration for vocabulary/hierarchy/mapping semantics, and SSSOM is an appropriate provenance-oriented model for mappings between vocabularies.

Do not import a giant external ontology into the core execution path.

Do not make schema.org, Wikidata, DBpedia, GeoNames, etc. the canonical internal world model.

They may be external semantic sources and mapping targets.

Schema.org is useful as a reference vocabulary because it distinguishes types, properties and enumerated values and deliberately allows broad/general types and multiple domains/ranges rather than forcing artificial classes. Treat it as an external vocabulary, not as the platform's authority.

---

# 3. FIRST CONSTITUTIONAL PRINCIPLE: MENTION ≠ ENTITY ≠ TYPE

Preserve the separation:

```text
Mention
Candidate
Entity
TypeHypothesis
TypeAssertion
RelationCandidate
RelationClaim
GraphNode
GraphEdge
```

must remain different concepts.

Never implement:

```text
mention.kind == entity.type
```

as an identity theorem.

Never implement:

```text
one mention = one entity
```

Never implement:

```text
one entity = one type
```

Never implement:

```text
one relation surface = one relation type
```

The same entity may simultaneously carry:

```text
core:Entity
core:Person
schema:Person
local:ResearchSubject
context:WebsiteAuthor
```

as different type assertions, scopes and evidence.

The same mention may have competing type hypotheses:

```text
Person      0.62
Organization 0.31
Unknown      retained
```

without any one being silently selected.

---

# 4. FOUNDATIONAL ATOMIC TYPE VOCABULARY

## 4.1 Introduce a versioned foundational type pack

Create a foundational local vocabulary, for example:

```text
core:
```

with a versioned pack.

Do not hard-code these as an enormous `Enum` unless the repository architecture explicitly requires that.

Prefer a versioned vocabulary object/pack compatible with the existing semantic vocabulary architecture.

The foundational vocabulary should have at minimum:

### Person / agent

```text
core:Person
core:Organization
core:LegalEntity
core:Group
core:Agent
```

### Web / digital

```text
core:WebSite
core:WebPage
core:OnlineAccount
core:SocialProfile
core:Domain
core:DigitalResource
```

### Place / geography

```text
core:PhysicalPlace
core:Facility
core:Address
core:GeographicRegion
core:Country
core:StateOrProvince
core:City
core:Coordinate
```

### Information

```text
core:Document
core:Dataset
core:CreativeWork
core:MediaResource
core:Software
core:Project
```

### Commercial / physical objects

```text
core:Product
core:Service
core:Asset
core:Vehicle
core:FinancialInstrument
```

### Events

```text
core:Event
```

### Values

Keep value objects conceptually separate from entity classes:

```text
value:EmailAddress
value:PhoneNumber
value:URL
value:Handle
value:Identifier
value:IPAddress
value:Hash
value:CryptoAddress
value:Date
value:DateTime
value:Money
value:Quantity
value:Coordinate
```

Do not force every value into `Entity`.

---

# 5. ATOMIC TYPE ≠ EXHAUSTIVE ONTOLOGY

The `core:*` vocabulary is deliberately small enough to be infrastructure.

It must be possible to extend it.

Example:

```text
core:Organization
    ↓
industry:Bank
    ↓
industry:CommercialBank
```

but the existence of `core:Organization` must never imply:

```text
everything unknown cannot be Organization
```

Unknown remains unknown.

Subtype relationships must be usable for:

* query expansion,
* blocking,
* ranking,
* validation,
* role matching.

They must not be used as an extraction gate.

---

# 6. TYPE HYPOTHESIS MODEL

The current `TypeHypothesis` in `semantic.blocking` is useful but too thin to be the whole interpretation mechanism.

Extend or complement it with a proper semantic type hypothesis representation.

Required conceptual fields:

```text
type_surface
normalized_surface
type_ref
scheme
hypothesis_state
confidence
source_ref
extractor_ref
extractor_version
evidence_refs
context_ref
semantic_regime_ref
mapping_candidates
```

States may be:

```text
UNKNOWN
OBSERVED
INFERRED
MAPPED
AMBIGUOUS
CONFLICTING
```

Do not confuse this with `SemanticStatus` on `TypeAssertion`.

The distinction is:

```text
TypeHypothesis
    = interpretation candidate

TypeAssertion
    = evidence-bearing semantic assertion
```

---

# 7. TYPE EXTRACTION SHOULD BECOME MULTI-SIGNAL

The current `TypedMention.kind: str` is too restrictive as the semantic endpoint.

Do NOT necessarily remove it immediately for compatibility.

Instead:

```text
TypedMention
    +
type_hypotheses[]
```

or equivalent.

The raw `kind` may be retained as legacy/coarse producer classification.

The actual semantic type layer should be capable of:

```text
surface "Apple"
    → Person hypothesis
    → Organization hypothesis
    → Product hypothesis
```

before resolution.

Likewise:

```text
"Tesla"
```

may produce:

```text
Organization
Vehicle
Product
```

depending on context.

This is not an error.

It is information.

---

# 8. ENTITY EXTRACTOR EXPANSION

Complete the deterministic extraction layer around actual atomic types.

Existing extractors must be adapted rather than duplicated into a second unrelated extraction framework.

At minimum provide producers/readers for:

### A. Person

Existing:

```text
persons.py
```

Improve:

* Latin names
* Cyrillic names
* initials
* multi-token names
* titles
* person-name contextual cues
* aliases
* transliteration
* Unicode normalization
* surname-first patterns
* social/profile names where useful

No assumption:

```text
name-shaped string == person
```

Every person result is a type hypothesis/mention observation.

### B. Organization

Existing:

```text
orgs.py
```

Extend beyond legal-form-only detection.

Recognize:

* legal-form patterns
* corporate suffixes
* institutional names
* brands
* agencies
* universities
* government bodies
* media organizations
* banks
* companies
* NGOs
* organizations inferred from strong contextual structures

Again:

```text
organization hypothesis
```

not:

```text
entity = organization
```

### C. WebSite / WebPage / Domain / URL

Create deterministic extraction for:

```text
https://example.com
example.com
www.example.com
```

and distinguish:

```text
URL
Domain
WebSite
WebPage
```

These are not interchangeable.

A URL string is a value.

A WebPage is a resource.

A WebSite is a higher-level resource.

A domain is a namespace/network resource.

Preserve the distinction.

### D. OnlineAccount / SocialProfile

Recognize structured profile URLs and handles.

Examples:

```text
github.com/user
twitter/x.com/user
linkedin.com/in/user
t.me/user
youtube.com/@channel
```

Do not infer account identity merely from a display name.

### E. Digital identifiers

Extend existing indicator extraction:

```text
IP
hash
CVE
crypto address
file path
identifier
```

into value-type hypotheses.

### F. Documents

Detect/documentize:

* URLs pointing to files
* filenames
* document IDs
* report-like structures
* PDFs/documents when source metadata provides them
* citations
* document title/identifier structure

### G. Event mentions

An event mention is not a relation.

Create event/entity hypotheses for:

```text
conference
meeting
acquisition
launch
publication
incident
transaction
election
appointment
```

But do not turn event words directly into claims.

---

# 9. STRUCTURED SEMANTICS MUST FEED TYPE HYPOTHESES

Add/extend structured semantic ingestion for:

```text
JSON-LD
schema.org
OpenGraph
RDFa
microdata
HTML metadata
```

A structured statement like:

```json
{
  "@type": "Person",
  "name": "John Smith"
}
```

must produce:

```text
TypeSignal(
    source_vocab = schema.org,
    surface = "Person",
    mapping_candidates = [...]
)
```

not immediately:

```text
TypeAssertion(core:Person)
```

External semantic vocabularies must go through explicit mapping.

Use a mapping structure compatible with the existing SSSOM-oriented architecture.

A mapping should retain:

```text
subject_type
object_type
mapping_predicate
mapping_set
mapping_version
confidence
creator/operator
evidence/provenance
```

Never collapse:

```text
schema:Person
```

into:

```text
core:Person
```

without a mapping record.

SSSOM exists precisely to represent mappings with match type, provenance and confidence rather than pretending every cross-vocabulary correspondence is exact equivalence.

---

# 10. TYPE ASSERTION PIPELINE

Implement/finalize:

```text
Observation
→ Mention
→ TypeSignal
→ TypeHypothesis
→ SemanticRegime interpretation
→ TypeAssertion
```

Maintain all previous states.

Example:

```text
raw surface:
"Apple"

TypeSignal:
surface = Apple

TypeHypothesis:
core:Organization
confidence=0.71

TypeHypothesis:
core:Product
confidence=0.22

Semantic mapping:
external schema candidate

TypeAssertion:
entity=ENT-...
type=core:Organization
scope=OBSERVED
status=OBSERVED
evidence=...
```

A later inference:

```text
status=INFERRED
```

must be a new revision, not destructive replacement.

This follows the existing `TypeAssertion` two-level identity model.

---

# 11. CRITICAL RELATION ARCHITECTURE

Now the major part.

The relation layer must NOT be redesigned as:

```text
relation vocabulary → extractor rules → GraphEdge
```

Instead:

```text
observable structure
→ RelationSignal
→ RelationCandidate
→ semantic interpretation
→ RelationClaimMaterial
→ RelationClaim
→ GraphEdge
```

OpenIE research explicitly treats relation extraction as deriving structured information without restricting relation types/domains; more recent work likewise explores extraction without assuming a known relation option set.

---

# 12. FIX THE SEMANTIC MEANING OF RelationSignal

A `RelationSignal` means:

> “This producer observed evidence that a particular relational configuration exists between these participant slots.”

It does NOT mean:

> “This relation definitely exists.”

And does NOT mean:

> “This is relation type X.”

And does NOT mean:

> “Create graph edge X.”

---

# 13. REWORK RelationSignal INTO A STRUCTURAL CONTRACT

Current `RelationSignal` is still too binary and too dependent on loose fields.

Introduce a first-class participant representation.

For example:

```python
@dataclass(frozen=True)
class RelationParticipant:
    mention_ref: str
    slot: str
    role_hypothesis: str = ""
    ordinal: int = 0
    confidence: float = 0.0
```

Then:

```python
participants: tuple[RelationParticipant, ...]
```

becomes canonical.

Legacy properties:

```python
subject_mention_ref
object_mention_ref
```

may remain as compatibility accessors for binary relations, but must be derived from participants.

The new model must support:

```text
2 participants
3 participants
4 participants
N participants
```

without inventing a fake binary decomposition.

---

# 14. RelationSignal REQUIRED FIELDS

The signal contract should explicitly support:

```text
signal_id
tenant_id

signal_kind

participants[]
role_hypotheses
arity_hypothesis
direction_hypothesis
polarity

relation_surface
predicate_surface
normalized_predicate
predicate_signature

relation_ref
predicate_hypothesis

trigger_span
supporting_spans
structural_path

temporal_evidence

observation_refs
evidence_refs

context_ref
semantic_regime_ref
capture_ref

producer_ref
producer_version
extraction_rule_id

producer_confidence

neighbourhood

signal_ordinal

extra
```

But:

### Do not turn the entire thing into arbitrary JSONB.

The load-bearing semantic dimensions must be typed.

`extra` is only for producer-specific non-core metadata.

---

# 15. SIGNAL KIND VOCABULARY

Fix the mismatch with FR-021.

The vocabulary must include at least:

```text
LEXICAL
SYNTACTIC
STRUCTURAL
METADATA
LINK
REFERENCE
TABLE
LIST
EVENT
TEMPORAL
ATTRIBUTE
CO_OCCURRENCE
SEMANTIC
```

Existing useful members may remain:

```text
COREFERENCE
SCHEMA
QUANTITY
NEGATION
```

but do not substitute them for the mandatory semantic categories.

Prefer to document which members represent:

```text
observation channel
```

versus:

```text
orthogonal signal aspect
```

Do not allow the enum to become an unstructured dumping ground.

Where appropriate introduce a separate:

```text
SignalAspect
```

for:

```text
NEGATION
TEMPORAL
QUANTITY
COREFERENCE
UNCERTAINTY
```

rather than continuing to overload `SignalKind`.

Make the smallest coherent change that eliminates semantic ambiguity.

---

# 16. RELATION SURFACE MUST NOT BE REQUIRED FOR EVERY SIGNAL

A co-occurrence signal may honestly have no predicate words.

For example:

```text
John Smith
Acme Corporation
```

appearing together can yield:

```text
signal_kind = CO_OCCURRENCE
relation_surface = ""
```

This is valid.

The signal still carries:

```text
why observed
where observed
participants
neighbourhood
evidence
```

Therefore remove any database/domain invariant of:

```text
relation_surface != "" OR relation_ref != NULL
```

when it makes CO_OCCURRENCE structurally impossible.

Replace it with:

```text
every signal must have an explicit observational basis
```

The basis may be:

```text
predicate text
DOM relation
table slot
hyperlink
citation
proximity
metadata field
event frame
attribute key
```

Unknown relation semantics are valid.

---

# 17. BIG IDENTITY FIX

This is mandatory.

Current `RelationCandidate.logical_candidate_id` must NOT depend on raw:

```text
relation_surface
```

because that violates the intended grammar-form independence.

The logical relation identity must represent:

```text
relational configuration
```

not:

```text
surface realization
```

Therefore remove raw `relation_surface` from logical candidate identity.

---

# 18. INTRODUCE PredicateSignature

Create a deterministic normalized representation:

```text
PredicateSignature
```

or equivalent.

It is NOT a RelationRef.

It is NOT a semantic ontology concept.

It is a structural/language-normalized signature.

It may contain:

```text
language
normalized_trigger
lemma
normalized_frame
normalized_argument_roles
voice_normalized
preposition_normalized
particle_normalized
event_class_hint
```

Example:

```text
John acquired Acme
```

and:

```text
Acme was acquired by John
```

must be able to produce the same:

```text
predicate_signature = acquire(...)
```

while retaining two distinct surface observations:

```text
"John acquired Acme"
"Acme was acquired by John"
```

as evidence.

The signature is the bridge between:

```text
raw linguistic realization
```

and:

```text
logical relational configuration
```

This is precisely the missing middle layer.

---

# 19. RAW SURFACE BELONGS TO REVISION/EVIDENCE, NOT LOGICAL IDENTITY

The logical candidate identity should approximately depend on:

```text
tenant
participant configuration
arity shape
role shape
directional configuration
polarity
predicate signature
```

and NOT on:

```text
raw relation_surface
producer
producer_version
signal_refs
capture
context
regime
confidence
status
temporal evidence
```

Those are revision/evidence material.

This gives:

```text
same logical relation
    ├── observation A: "is CEO of"
    ├── observation B: "became CEO of"
    └── observation C: "was appointed CEO of"
```

without making every linguistic realization a distinct world relation.

---

# 20. DO NOT FORCE SEMANTIC EQUIVALENCE WHERE IT IS UNKNOWN

A normalized signature is not magical semantic reasoning.

Do not do:

```text
owns
controls
manages
```

→ same relation

just because they sound similar.

Only unify when deterministic normalization or explicit semantic mapping establishes that configuration.

The principle is:

```text
surface variation
≠
semantic equivalence

but

surface variation
must not itself force
semantic inequality
```

That is the correct interpretation of FR-040.

---

# 21. PredicateHypothesis BECOMES A TRUE OPEN-WORLD LAYER

`PredicateHypothesis` should preserve:

```text
surface_form
normalized_form
predicate_signature
relation_ref
alternative_refs
resolution_state
mapping_evidence_refs
```

States:

```text
KNOWN
UNKNOWN
AMBIGUOUS
CONFLICTING
```

No sentinel:

```text
UNKNOWN_RELATION
```

No fake `RelationRef` for unknown predicates.

For:

```text
"originator of"
```

the honest state is:

```text
surface = originator of
relation_ref = None
state = UNKNOWN
```

not:

```text
relation_ref = local:unknown_relation
```

---

# 22. RELATION CANDIDATE = DURABLE HYPOTHESIS

Do not introduce another identity level just for aesthetics.

The preferred model is:

```text
RelationSignal
    ↓
RelationCandidate
```

where `RelationCandidate` is the durable hypothesis object.

Do NOT create:

```text
Signal
→ Hypothesis
→ Candidate
→ CandidateRevision
→ CandidateVersion
```

unless a concrete persistence requirement forces it.

Keep:

```text
CAND-
CNDR-
```

as the two-level candidate identity.

---

# 23. Candidate identity partition

Logical candidate:

```text
CAND-
```

answers:

> Which relational configuration are we talking about?

Revision:

```text
CNDR-
```

answers:

> Which reading of that configuration was recorded?

Logical material must not include:

```text
relation_surface
producer
signal_refs
extractor version
regime
context
confidence
status
evidence order
observation timestamp
```

Revision material may contain them.

The candidate must preserve every surface and signal through revision/evidence links.

---

# 24. FIX THE CURRENT CONFLATION OF PRODUCER AND OBSERVATION

There is a semantic bug in the current implementation/docs:

`RelationSignal._material()` includes `producer_ref`, so two different producers intentionally produce different signal IDs.

That is actually correct.

Do not "fix" it by globally deduping:

```text producer A
producer B
```

into one signal.

Correct semantics:

```text same producer + same observed structure
    → same signal identity

different producer + same observed structure
    → different signal identities
    → possible corroboration
```

FR-034 independence requires the second behaviour.

Therefore:

```text signal_id
```

is producer-specific.

The candidate aggregates:

```text signal_refs = [signal-A, signal-B, signal-C]
```

and independence is computed over:

```text producer_ref / independence_family
```

not over deduplicated signal content.

Correct the misleading docstrings/tests.

---

# 25. MENTION REFERENCES MUST BE REAL

Current producers still use synthetic things such as:

```text
surface:role:john smith
document:current
meta:author:...
```

in fields named:

```text
*_mention_ref
```

This is not acceptable as final architecture.

Implement a pre-resolution mention index/addressing seam.

The flow must be:

```text
text/html/table
    ↓
mention extraction
    ↓
MentionRegistry / MentionIndex
    ↓
producer receives access to actual mentions
    ↓
RelationSignal references actual mention IDs
```

This is NOT entity resolution.

It is only:

```text
surface occurrence
→ already extracted mention
```

No producer may invent a mention identity from text after the mention stage.

If a structural producer observes a value that was not represented as a mention yet:

```text
do not invent the mention_id
```

Instead record the structural raw slot and produce a typed/deferred participant reference that can be bound by an explicit mention-binding stage.

Do not silently synthesize fake mention IDs.

---

# 26. Introduce MentionBinding

Implement something equivalent to:

```text
MentionOccurrenceIndex
```

with deterministic lookup on:

```text
capture
segment
offset/span
normalized surface
extractor occurrence
```

A structural producer can say:

```text
HTML anchor source span X
```

and the mention binding stage resolves that to:

```text
MENTION-...
```

without resolving it to an entity.

This restores:

```text
Observation
→ Mention
→ RelationSignal
```

instead of:

```text
Observation
→ fake surface identity
→ RelationSignal
```

---

# 27. UNIVERSAL RELATION EXTRACTION IS A COMMON OBSERVATION SPACE

Do not interpret "universal relation extraction" as:

> write 500 relation-specific extractors.

Interpret it as:

> expose one common relational observation language to which many heterogeneous instruments can contribute.

Required producer families:

```text
LEXICAL
SYNTACTIC
STRUCTURAL
LINK
REFERENCE
TABLE
LIST
METADATA
ATTRIBUTE
EVENT
TEMPORAL
CO_OCCURRENCE
SEMANTIC
```

The downstream model is identical.

---

# 28. LEXICAL PRODUCER

Existing:

```text
apps/interpretation/extractors/signals/lexical.py
```

must remain one producer.

Upgrade it to produce:

```text
raw predicate surface
normalized predicate
predicate signature
participant roles
direction hypothesis
arity
trigger/support evidence
```

The existing `RELATION_CUES` becomes only one lexical instrument.

Do not delete it.

Do not let it define the global relation vocabulary.

---

# 29. SYNTACTIC PRODUCER

Introduce:

```text
extractors/signals/syntactic.py
```

or equivalent.

The producer should exploit dependency/constituency information when available.

Support at least:

### Active

```text
John acquired Acme.
```

### Passive

```text
Acme was acquired by John.
```

### Copular

```text
John is the CEO of Acme.
```

### Nominal

```text
John, CEO of Acme, ...
```

### Appositional

```text
John Smith, CEO of Acme, ...
```

### Possessive

```text
Acme's founder John Smith
```

### Prepositional

```text
John works at Acme.
```

### Relative clause

```text
John, who founded Acme, ...
```

The producer should produce structural/predicate signatures and role hypotheses.

It must NOT directly emit `works_for`, `founded`, `owner_of`, etc. unless the lexical/semantic mapping layer explicitly says so.

---

# 30. SYNTACTIC PARSER DEPENDENCY

Inspect currently installed parser capabilities.

Prefer a deterministic/pinned parser interface.

Do not introduce an LLM into the constitutional extraction path.

If an external parser/model is introduced:

```text
model_ref
model_version
parser_version
configuration_hash
```

must be explicit and part of interpretation provenance.

For deterministic baseline, produce useful relation signals even when parser output is unavailable.

A missing parser capability must mean:

```text
no syntactic signals
```

not:

```text
batch failure
```

unless the contract explicitly says the parser is mandatory.

---

# 31. STRUCTURAL PRODUCER

Introduce a producer for non-linguistic document structure.

Examples:

```text
DOM parent/child
section membership
heading → content block
breadcrumb
caption → table
figure → caption
document → subsection
page → document
```

Represent:

```text
structural_path
```

rather than flattening structure into a fake predicate.

Example:

```text
<h2>Board of Directors</h2>
<div>John Smith</div>
```

can yield:

```text
STRUCTURAL signal
participant = John Smith
context = Board of Directors section
```

It should not automatically emit:

```text
member_of_board
```

---

# 32. LINK PRODUCER

Existing link producer must remain.

Required semantics:

```text
A links to B
```

is observed structure.

Not:

```text
A cites B
A owns B
A references B semantically
A hosts B
```

unless another interpretation establishes it.

Preserve:

```text
source mention
target/resource mention
href
anchor text
DOM path
link position
rel attribute
target metadata
```

`rel="author"` may become a stronger semantic signal, but it is still an interpretation candidate, not an immediate RelationClaim.

RDF-style statement annotation is relevant here because the relation itself may later need metadata about provenance/context; RDF 1.2 is currently evolving around precisely this class of statement-level representation.

---

# 33. REFERENCE / CITATION PRODUCER

Support:

```text
footnotes
references
citation markers
"see ..."
"as described in ..."
DOI/reference patterns
document IDs
```

Output:

```text
REFERENCE signal
```

not automatically:

```text
cites
```

A reference observation can later map to one or several semantic interpretations.

---

# 34. TABLE PRODUCER

Tables are especially important.

A table:

```text
Person | CEO | Company
John   | CEO | Acme
```

must produce structural participant/role evidence.

Do not require an ontology relation before emitting the signal.

The header:

```text
CEO
```

is an observed slot/surface.

The row:

```text
John | CEO | Acme
```

is structural evidence for an n-ary configuration.

Preserve:

```text
table_ref
row_ref
column_ref
header_ref
cell_ref
participant_ref
```

Malformed tables must be refused/skipped according to explicit structural rules, never positionally guessed.

---

# 35. LIST PRODUCER

Support:

```text
Founder:
- John Smith
- Jane Doe

Board:
- John Smith
- Acme Representative
```

Produce structure, role hints and participant slots.

Do not directly create semantic relations.

---

# 36. METADATA PRODUCER

Existing metadata producer should cover:

```text
author
publisher
creator
canonical URL
site
section
category
parent
path
domain
```

plus unrecognized metadata.

Unknown metadata must survive.

Do not map:

```text
author → authored_by
```

automatically.

Produce:

```text
attribute/metadata signal
```

and let semantic interpretation decide.

---

# 37. ATTRIBUTE PRODUCER

Represent:

```text
Role: CEO
Status: Active
Industry: Banking
Founded: 1998
```

as attribute observations.

The value must NOT automatically become an entity.

Distinguish:

```text
entity → scalar value
entity → typed value
entity → entity
```

explicitly.

This is essential.

---

# 38. TEMPORAL PRODUCER

Temporal expressions must become evidence associated with a relation signal/hypothesis.

Examples:

```text
John acquired Acme in 2020.
```

should produce:

```text
relation signal
temporal evidence:
    surface = "in 2020"
    normalized interval = ...
    precision = YEAR
    evidence span = ...
```

Do not silently promote inferred temporal interval into world truth.

Respect existing `TemporalHypothesis` and `SourceTemporalObservation`.

---

# 39. EVENT PRODUCER

This is mandatory.

Support n-ary event structures.

Example:

```text
John sold Acme to Microsoft in 2020.
```

Do NOT reduce immediately to:

```text
John → sold → Acme
Acme → sold_to → Microsoft
```

Instead represent:

```text
EventCandidate
participants:
    seller = John
    asset = Acme
    buyer = Microsoft
    time = 2020
```

At relation-substrate level this can be represented as an n-ary `RelationCandidate` if that is the least invasive path.

But preserve the event/role structure.

A binary graph projection may later derive selected edges according to an explicit projection policy.

The original event structure must never be discarded.

---

# 40. CO-OCCURRENCE

Support:

```text
A and B appear in the same sentence/block/window
```

as an observation.

Never convert:

```text
CO_OCCURRENCE
```

to:

```text
related_to
```

automatically.

The signal can be useful for:

* blocking,
* discovery,
* hypothesis generation,
* query expansion,
* contextual reconstruction.

It is not an asserted relation.

---

# 41. NEGATION

Represent:

```text
Acme did not acquire Beta.
```

as positive structural evidence of a denied relation.

Do not:

```text
drop negative
```

and do not:

```text
create positive acquisition edge
```

The signal must contain:

```text
polarity = DENIED
```

and preserve the underlying predicate surface/signature.

---

# 42. SEMANTIC PRODUCER

The semantic producer may consume:

```text
schema.org
JSON-LD
mapping systems
domain vocabularies
profile annotations
```

but only to create predicate/type interpretation candidates.

It must never:

```text
ontology match
→ automatic truth
```

This is an interpretation layer.

---

# 43. MULTIPLE SIGNALS → ONE HYPOTHESIS

If:

```text
lexical producer
```

and:

```text
table producer
```

and:

```text
structured metadata producer
```

all support the same participant configuration, the assembly layer should be capable of creating:

```text
ONE logical candidate
MANY signals
```

where appropriate.

But only when they describe the same relational configuration.

---

# 44. DIFFERENT RELATIONS MUST NOT MERGE

Example:

```text
John → CEO of → Acme
John → founded → Acme
```

must not merge just because endpoints are equal.

The predicate signature/configuration is different.

So:

```text
candidate A
candidate B
```

remain distinct.

Likewise:

```text
John owns Acme
```

and:

```text
Acme hosts John's website
```

are not one hypothesis.

---

# 45. CONFLICTS MUST NOT BE MAJORITY-VOTED

Current `_arity_of()` uses a majority vote.

Remove that semantic behaviour.

Never:

```text
producer A = NARY
producer B = NARY
producer C = DIRECTED

→ NARY because 2 > 1
```

Deterministic majority voting is not a truth criterion.

Instead:

```text
candidate/hypothesis A
candidate/hypothesis B
```

or:

```text
one ambiguous candidate with explicit alternatives
```

depending on the nature of the disagreement.

Assembly may normalize.

Assembly may aggregate.

Assembly may detect conflict.

Assembly must not adjudicate semantics by vote.

---

# 46. HARD BLOCKING

Candidate generation must follow:

```text
GENERATE WIDE WITHIN BOUNDED STRUCTURAL NEIGHBOURHOODS
        ↓
HARD BLOCK
        ↓
RESOLVE
        ↓
SEMANTIC INTERPRETATION
        ↓
VALIDATE
        ↓
ADMIT
```

Never:

```text
all mentions × all mentions
```

.

Required neighbourhood classes:

```text
same sentence
same segment
same paragraph/block
dependency-connected
DOM-local
table-local
list-local
metadata-local
event-participant
reference-local
explicit link
```

Each signal must state its actual neighbourhood.

---

# 47. COST MODEL

Every producer must expose/report:

```text
characters_scanned
tokens_scanned if meaningful
candidate_pairs_considered
structural_nodes_considered
signals_emitted
```

Do not claim "bounded" merely because a function eventually checks a counter after doing the work.

The implementation itself must remain bounded.

Per-document / per-segment hard ceilings must be explicit.

---

# 48. RELATION CANDIDATE ASSEMBLY

`RelationSignalAssembler` should:

1. group by structural participant configuration,
2. preserve direction,
3. preserve polarity,
4. preserve predicate signature,
5. preserve all signal refs,
6. construct candidate hypothesis,
7. preserve alternative interpretations,
8. detect conflicts,
9. never resolve entities,
10. never admit claims,
11. never create GraphEdge.

---

# 49. PREDICATE ALTERNATIVES

Example:

```text
signal A:
surface = CEO of
relation_ref = employment

signal B:
surface = CEO of
relation_ref = organizational_role
```

should be representable as:

```text
PredicateHypothesis:
    surface = CEO of
    primary = ...
    alternatives = [...]
    state = AMBIGUOUS
```

without overwriting either interpretation.

If evidence genuinely disagrees:

```text
state = CONFLICTING
```

and preserve both.

---

# 50. CLAIM MATERIAL BOUNDARY

`RelationClaimMaterial` may only be built when:

```text
predicate resolved sufficiently for the claim schema
+
participants resolved
+
required role structure known
```

Unknown predicate candidates remain durable candidates.

Do NOT invent a local relation type simply to make them eligible for GraphEdge.

Unknown relation:

```text
RelationCandidate ✅
ClaimMaterial      ❌ until resolved
RelationClaim      ❌
GraphEdge          ❌
```

This is intentional.

The extracted structural information remains available.

---

# 51. GRAPH EDGE IS A PROJECTION

Graph projection remains:

```text
RelationClaim
→ GraphEdge
```

never:

```text
RelationSignal
→ GraphEdge
```

and never:

```text
RelationCandidate
→ GraphEdge
```

The graph is a projection.

The evidence/hypothesis substrate is the durable semantic substrate.

Wikidata's model is a useful external precedent here: the statement is the central unit, with qualifiers and references extending its context rather than pretending the bare triple contains the whole epistemic state.

---

# 52. BINARY GRAPH PROJECTION

For:

```text
DIRECTED
```

project:

```text
GraphEdge(
    edge_id = relation_id,
    source = subject_ref,
    target = object_ref,
    ...
)
```

preserving direction.

Never canonicalize:

```text
min(source,target)
max(source,target)
```

for directed edges.

---

# 53. UNDIRECTED GRAPH PROJECTION

For truly symmetric relations:

```text
UNDIRECTED
```

projection may use canonical endpoint ordering.

But only if the admitted relation contract declares symmetry.

Do not infer symmetry merely because the extractor did not know direction.

---

# 54. N-ARY GRAPH PROJECTION

For:

```text
NARY
```

use:

```text
HyperEdge
```

or the existing native n-ary projection abstraction.

Do not flatten an n-ary relation into a set of binary edges unless:

1. the projection policy explicitly permits it,
2. the original hyperrelation remains available,
3. the derived edges reference the source relation claim.

---

# 55. ATTRIBUTE GRAPH PROJECTION

Do not force:

```text
Person → email → EmailAddress
```

into a normal entity graph if the object is a scalar value.

Support a clear distinction between:

```text
Entity → Entity
Entity → Value
```

inside the relation claim/projection layer.

---

# 56. OBSERVATION GRAPH VS WORLD GRAPH

If the platform needs to visualize extracted-but-unadmitted relationships, create an explicit observation/hypothesis view.

For example:

```text
RelationEvidenceView
```

or equivalent.

Do NOT misuse `GraphEdge`.

Possible conceptual layers:

```text
WORLD GRAPH
    admitted RelationClaims
    ↓
GraphEdge / HyperEdge

HYPOTHESIS GRAPH
    RelationCandidates
    ↓
candidate visualization

EVIDENCE GRAPH
    RelationSignals / lineage
    ↓
provenance/diagnostic visualization
```

These are different projections.

Do not collapse them.

---

# 57. FIX EXECUTABLE PATH

This is mandatory.

The current path must stop doing:

```text
candidate
→ build
→ validate
→ admit
→ claim
→ validate again
```

Replace with real stages:

```text
OBSERVATION
CONTEXT
MENTIONS
TYPE SIGNALS / TYPES AS APPROPRIATE
REGIME
RELATION SIGNALS
RELATION CANDIDATE
RESOLUTION
CLAIM MATERIAL
VALIDATION
ADMISSION
STORE
EDGE
WORLDLINE
```

At minimum the executable order must make the actual claim lifecycle:

```text
Candidate
→ ClaimMaterial
→ Validation
→ Admission
→ RelationClaim
```

and never:

```text
RelationClaim
→ Validation
```

as the primary lifecycle.

Do not retain a fake `SUPPORTED` technical gate.

---

# 58. MATERIAL MUST BE A REAL EXECUTION OBJECT

If required, extend `ExecutionResult`:

```text
candidate
material
validation
admission
claim
edge
worldline
```

Every stage must expose the actual object it produced.

A stage that is semantically "material" but silently performs validation/admission is not acceptable.

---

# 59. PERSISTENCE

Feature 020 created the storage tables.

Feature 021 must finish the application persistence path.

Implement durable store seams for:

```text
RelationSignal
RelationCandidate
SourceTemporalObservation
```

with:

```text
write
get
by_tenant
by_logical_id
by_pair
by_signal
checksum/replay support
```

where architecturally appropriate.

Every store must reconstruct the exact domain object.

Round-trip:

```text
domain
→ row
→ database
→ row
→ domain
```

must preserve the complete semantic information.

---

# 60. PREDICATE HYPOTHESIS PERSISTENCE

Do not hide:

```text
alternative_refs
mapping_evidence
predicate_signature
resolution_state
normalized predicate
```

inside an opaque 64-byte digest only.

If `PredicateHypothesis` is content-addressed but not independently persisted, make sure the owning Candidate revision stores enough structured data to reconstruct it losslessly.

A digest may identify data.

A digest must not be the only copy of the data required for reconstruction.

---

# 61. TEMPORAL PERSISTENCE

Finish:

```text
capture_with_observations()
```

so that the normal acquisition production path can actually persist:

```text
SourceTemporalObservation
```

Do not leave temporal observations reachable only through a new helper nobody uses.

The path must be:

```text
adapter
→ Capture + SourceTemporalObservation
→ durable store
```

for applicable sources.

EDGAR:

```text
date_filed
```

must remain day precision.

Common Crawl:

```text
timestamp
```

must remain index-observation time rather than publication time.

Do not stuff source publication time into `Capture.fetched_at`.

---

# 62. MIGRATION

Create the next forward-only migration if required.

Do not modify applied migrations.

Migration must:

* preserve data,
* be tenant scoped,
* add explicit CHECKs only where they encode constitutional invariants,
* keep ORM/migration parity,
* never drop historical semantic observations.

Create:

```text
migration parity tests
schema invariants
round-trip tests if PostgreSQL available
```

---

# 63. FOUNDATION PACK

Create a small foundational pack such as:

```text
core-atomic-types@1
```

with the atomic type definitions above.

Each type needs:

```text
type_ref
label
alt_labels
broader_refs
narrower_refs
description
kind = entity/value
version
```

Do not encode massive relation semantics into the type pack.

The pack may contain:

```text
blocking hints
```

but not truth.

---

# 64. TYPE MAPPINGS

Add initial mappings for common external vocabularies where justified:

```text
schema:Person → core:Person
schema:Organization → core:Organization
schema:WebSite → core:WebSite
schema:WebPage → core:WebPage
schema:Event → core:Event
schema:Product → core:Product
schema:SoftwareApplication → core:Software
```

Treat these as explicit mappings.

Do not silently treat mappings as exact equivalence if they are not.

Use SSSOM-compatible semantics where practical.

---

# 65. RELATION VOCABULARY POLICY

Do not create a gigantic mandatory internal relation enum.

The semantic relation registry may still contain known operators such as:

```text
works_for
owns
controls
founded
located_in
reports_to
created
published
employs
```

because known operators are useful.

But the registry's purpose is:

```text
semantic interpretation
validation contract
role hints
blocking
projection contract
```

not:

```text
enumeration of reality
```

The unknown relation surface remains valid even if no registry operator exists.

---

# 66. RELATION SIGNAL → KNOWN OPERATOR

The following mapping should be possible:

```text
signal:
    predicate_surface = "works at"
    predicate_signature = normalized employment frame
    relation_ref = none

semantic regime:
    mapping candidate = works_for

predicate hypothesis:
    relation_ref = works_for
```

Only after explicit semantic interpretation should the relation become typed.

---

# 67. RELATION SIGNAL → UNKNOWN OPERATOR

The following must also be possible:

```text
signal:
    surface = "originator of"
    normalized = originator
    signature = originator(...)
    relation_ref = None

candidate:
    predicate_state = UNKNOWN
```

The candidate must survive.

The relation is not discarded.

The platform must be able to answer:

```text
what participants were observed?
what structure connected them?
what words were used?
what type was unknown?
what alternative readings existed?
what source produced it?
what extractor produced it?
what temporal evidence existed?
```

This is CD-7 / FR-052.

---

# 68. RELATION SIGNAL PROVENANCE

Each signal must be traceable:

```text
signal
→ producer
→ source observation
→ capture
→ segment/document
```

The current evidence/derivation lineage distinction remains.

Do not turn:

```text
candidate
```

into an evidence hop merely because it explains a claim.

Candidate is derivation.

---

# 69. LINEAGE

Keep two conceptual directions:

```text
EVIDENCE LINEAGE
world assertion
→ supporting observation
→ source

DERIVATION LINEAGE
observation
→ interpretation
→ candidate
→ material
→ claim
→ projection
```

Candidate is not evidence.

Signal is evidence-bearing interpretation output.

Claim is admitted semantic state.

GraphEdge is projection artifact.

---

# 70. RELATION EXTRACTION FROM HTML

Build a real end-to-end corpus:

### Example 1

```html
<p>John Smith became CEO of Acme.</p>
```

Expected:

```text
mentions:
    John Smith
    Acme

signals:
    lexical
    syntactic if available

candidate:
    predicate_signature = CEO-role relation
```

### Example 2

```html
<p>Acme was acquired by John Smith.</p>
```

Expected:

```text
same logical relational configuration
distinct surface evidence
```

### Example 3

```html
<a href="/acme">Acme</a>
```

Expected:

```text
LINK signal
```

not:

```text
owns
cites
employs
```

### Example 4

```html
<table>
<tr><th>CEO</th><th>Company</th></tr>
<tr><td>John Smith</td><td>Acme</td></tr>
</table>
```

Expected:

```text
TABLE signal
role evidence
participant evidence
unknown/unmapped predicate allowed
```

### Example 5

```text
Founder: John Smith
```

Expected:

```text
ATTRIBUTE signal
```

with value semantics.

### Example 6

```text
John sold Acme to Microsoft in 2020.
```

Expected:

```text
EVENT/NARY candidate
seller = John
asset = Acme
buyer = Microsoft
temporal evidence = 2020
```

No binary information loss.

---

# 71. ENTITY-RELATION INTERACTION

The extraction system must support:

```text
mention A
    ↕
multiple type hypotheses

mention B
    ↕
multiple type hypotheses

relation signal
    ↕
role hypotheses
    ↕
candidate
```

Then resolution/blocking can exploit type hypotheses.

Example:

```text
works_for
subject:
    Person-like
    Account-like

object:
    Organization-like
    LegalEntity-like
```

This is a **blocking hint**.

It does not become truth.

---

# 72. NO GLOBAL O(N²)

Explicitly add mutation tests that catch:

```text
for mention_a in mentions:
    for mention_b in mentions:
```

in relation extraction.

Allowed pair generation must come from bounded structural neighbourhoods.

The system must remain practical on long documents.

---

# 73. NO HIDDEN SEMANTIC GATE

Explicitly grep and test that extraction cannot call:

```text
OntologyPack.allows_type()
```

as a drop/deny decision.

Also ensure relation extraction does not contain:

```text
if relation not in registry:
    continue
```

or equivalent.

Unknown semantic space must survive.

---

# 74. NO GRAPH IMPORTS IN PRODUCERS

Every producer module must fail structural import tests if it imports:

```text
GraphEdge
HyperEdge
GraphStore
RelationClaim
admission
projection
```

The only exception should be TYPE_CHECKING where appropriate and never executable code.

---

# 75. NO ENTITY IDS IN PRODUCERS

Producers may use:

```text
Mention IDs
```

after the mention-binding stage.

They may never use:

```text
ENT-
RES-
```

.

Entity resolution remains downstream.

---

# 76. TYPE EXTRACTION MAY USE ONTOLOGY HINTS

Unlike relation predicates, entity types are allowed to use:

```text
core:* vocabulary
external type mappings
type hierarchy
```

as extraction/interpetation aids.

But an ontology miss must mean:

```text
unknown type
```

not:

```text
mention rejected
```

---

# 77. CONTEXT-AWARE TYPE RESOLUTION

Add context inputs where already available:

```text
document title
section heading
DOM parent
table heading
neighbour mentions
URL/domain
metadata
language
```

Example:

```text
"Apple"
```

inside:

```text
iPhone
MacBook
iOS
```

may strengthen:

```text
Organization
```

while:

```text
red apple
fruit
nutrition
```

may strengthen:

```text
Product/PhysicalObject
```

Do not encode this as a universal deterministic truth rule unless a concrete extractor proves it.

Represent competing hypotheses and evidence.

---

# 78. GRAPH SEMANTICS

The graph layer should represent:

```text
admitted world relations
```

not:

```text
everything extraction ever saw
```

For every edge, the system must be able to navigate back to:

```text
RelationClaim
Candidate
Signals
Observations
Source
```

and in the reverse direction:

```text
Source
→ Observations
→ Signals
→ Candidates
→ Claims
→ GraphEdges
```

This makes graph projection rebuildable.

---

# 79. GRAPH EDGE PROPERTIES

Projection should preserve enough metadata to answer:

```text
which claim generated this edge?
which relation revision?
which logical relation?
which ontology/predicate interpretation?
which evidence?
which temporal interval?
which semantic regime?
which validation?
which source independence?
```

Do not put all of this into edge identity.

Use:

```text
edge_id = relation_id
```

where the existing graph architecture requires it.

Properties may carry the claim representation/provenance.

---

# 80. RDF / GRAPH INTEROPERABILITY

Do not make RDF the internal model.

But make the representation compatible in spirit with:

```text
subject
predicate
object
```

for binary claims,

and statement-level annotation for provenance/qualifiers.

RDF 1.2 currently develops triple terms so statements can themselves participate in further statements; this is useful interoperability inspiration for evidence-bearing claims, but the platform's own domain model remains authoritative.

---

# 81. SHACL

Keep SHACL as an optional validation/interoperability sidecar.

Do not move the extraction substrate into SHACL.

SHACL is shape validation, not the semantic substrate.

The current W3C SHACL 1.2 work is still a Working Draft, so do not make the core architecture depend on draft-only behaviour.

---

# 82. TEST CORPUS — ENTITY TYPES

Add a deterministic golden corpus covering:

```text
John Smith
Acme Corporation
Acme
Apple
Apple Inc.
example.com
https://example.com/a
@johnsmith
john@example.com
+370...
192.168.1.1
CVE-...
Bitcoin address
New York
Lithuania
University of ...
GitHub profile
LinkedIn profile
PDF/report
dataset
software repository
event
product
service
vehicle
financial instrument
```

Include ambiguity:

```text
Apple
Amazon
Jordan
Washington
Mercury
```

where reasonable.

Each case should test:

```text
raw mention
type hypotheses
mapped type
unknown types
alternative types
no entity resolution assumption
```

---

# 83. TEST CORPUS — RELATIONS

Minimum relation corpus:

### Text

```text
John works for Acme.
Acme employs John.
John is CEO of Acme.
Acme's CEO is John.
John, CEO of Acme, ...
John founded Acme.
Acme was founded by John.
John owns Acme.
Acme owns John.   # direction conflict / semantically different
```

### Events

```text
John sold Acme to Microsoft in 2020.
John joined Acme in 2018.
John was appointed CEO of Acme in March.
```

### Structural

```text
HTML link
HTML hierarchy
heading
breadcrumb
table
list
metadata
JSON-LD
schema.org
citation
reference
```

### Unknown

```text
John is the originator of Acme.
```

with:

```text
relation_ref=None
```

### Ambiguous

Same surface mapped by two semantic regimes/operators.

### Conflicting

Two incompatible signals over same participant structure.

---

# 84. ACTIVE/PASSIVE IDENTITY TEST

This is mandatory.

Create:

```text
case_active
case_passive
```

such that:

```text
John acquired Acme.
```

and:

```text
Acme was acquired by John.
```

produce:

```text
same logical_candidate_id
```

while:

```text
signal IDs differ
surface evidence differs
candidate revision evidence differs
```

Do not simply hard-code the two fixtures to the same ID.

The identity derivation itself must make this possible.

---

# 85. SAME RELATION, DIFFERENT PRODUCERS

Test:

```text
lexical producer
table producer
schema producer
```

all producing evidence for one relation.

Expected:

```text
1 logical candidate
N signal IDs
1+ candidate revisions as appropriate
```

Do not dedupe producers away.

---

# 86. DIFFERENT RELATIONS, SAME ENDPOINTS

Test:

```text
John works_for Acme
John founded Acme
John owns Acme
```

Expected:

```text
three logical hypotheses
```

not one candidate with three signals.

---

# 87. NEGATIVE TEST

Input:

```text
John did not acquire Acme.
```

Expected:

```text
predicate signature = acquire
polarity = denied
```

and no positive claim unless an independent positive observation exists.

---

# 88. N-ARY TEST

Input:

```text
John sold Acme to Microsoft in 2020.
```

Expected candidate:

```text
arity = NARY
roles:
    seller
    asset
    buyer
temporal evidence:
    2020
```

Any binary projections must reference the source n-ary claim.

---

# 89. ATTRIBUTE TEST

Input:

```text
John Smith
Role: CEO
```

Expected:

```text
ATTRIBUTE signal
value = CEO
```

Do not assume:

```text
CEO is entity
```

unless separately extracted as a type/entity.

---

# 90. UNKNOWN TEST

Input:

```text
John is the originator of Acme.
```

Expected:

```text
relation_surface = originator of
predicate_state = UNKNOWN
relation_ref = None
candidate exists
no claim yet
no GraphEdge
```

All evidence remains available.

---

# 91. PERSISTENCE TEST

For every new substrate object:

```text
build
→ store
→ read
```

must preserve:

```text
IDs
alternatives
signals
provenance
type hypotheses
predicate signature
temporal evidence
tenant
context
regime
```

Do not reduce it to a summary string.

---

# 92. REPLAY TEST

Required:

```text
run
→ record log
→ replay
→ replay again
```

and:

```text
signal ids identical
candidate ids identical
material identities identical
claim identities identical
edge ids identical
```

No:

```text
uuid.uuid4()
datetime.now()
dict-order-dependent output
random tie breaking
```

---

# 93. MUTATION TESTS

Add constitutional mutation harness for:

### Entity layer

Break:

```text
type_ref
entity_ref
tenant
evidence
mapping
status
```

and ensure specific tests detect the corruption.

### Relation layer

Break:

```text
predicate_signature
participants
roles
polarity
producer identity
signal evidence
candidate identity
surface exclusion from logical identity
```

and ensure tests fail.

### Projection

Break:

```text
direction
arity
claim provenance
edge identity
```

and ensure tests detect it.

---

# 94. PARTICULAR MUTATION: RAW SURFACE IN LOGICAL ID

Create a mutation that adds:

```text
relation_surface
```

to logical identity material.

The constitutional test must fail.

This is essential because otherwise someone will reintroduce the old FR-040 violation in six months.

---

# 95. PARTICULAR MUTATION: MAJORITY VOTE

Create conflicting arity/direction signals.

Mutation:

```text
majority vote wins
```

must fail the expected conflict-preservation test.

---

# 96. PARTICULAR MUTATION: SYNTHETIC MENTION

Mutation:

```text
surface:person:john
```

instead of actual `MENTION-*`

must fail the producer/mention binding contract.

---

# 97. PARTICULAR MUTATION: UNKNOWN TYPE DROPPED

Mutation:

```text
if core pack does not know type:
    continue
```

must fail.

Unknown semantic types remain observations.

---

# 98. PARTICULAR MUTATION: UNKNOWN RELATION DROPPED

Mutation:

```text
if relation_ref is None:
    return ()
```

must fail.

---

# 99. PARTICULAR MUTATION: PRODUCER → EDGE

Mutation test must fail if any extractor imports:

```text
GraphEdge
```

or constructs it.

---

# 100. SPEC / ADR UPDATES

Create or update:

```text
specs/021-entity-relation-extraction-finalization/
```

with:

```text
spec.md
plan.md
tasks.md
data-model.md
checklists/requirements.md
contracts/
research.md
```

At minimum record these ADR-level decisions:

### ADR A

Bounded foundational atomic entity vocabulary is allowed and desirable for interpretation.

### ADR B

Entity/value type vocabulary is separate from relation vocabulary.

### ADR C

Relation extraction is open-world and signal-driven.

### ADR D

Raw relation surface is evidence, not logical identity.

### ADR E

PredicateSignature is structural normalized relation identity before ontology mapping.

### ADR F

Unknown predicates are durable hypotheses.

### ADR G

N-ary relations are native.

### ADR H

GraphEdge is projection of admitted claims only.

### ADR I

Mention binding is distinct from entity resolution.

### ADR J

No majority-vote semantic assembly.

### ADR K

Producers remain observation instruments.

---

# 101. RECOMMENDED FINAL DOMAIN MODEL

The conceptual model after Feature 021 should read approximately:

```text
OBSERVATION
    │
    ▼
CONTEXT
    │
    ▼
MENTION OCCURRENCES
    │
    ├──────────────► TYPE SIGNALS
    │                    │
    │                    ▼
    │               TYPE HYPOTHESES
    │                    │
    │                    ▼
    │               TYPE ASSERTIONS
    │
    ▼
RELATION SIGNALS
    │
    │  lexical
    │  syntactic
    │  structural
    │  link
    │  reference
    │  table
    │  list
    │  metadata
    │  attribute
    │  event
    │  temporal
    │  co-occurrence
    │  semantic
    │
    ▼
RELATION CANDIDATE
    │
    ├── participants
    ├── roles
    ├── arity
    ├── polarity
    ├── predicate signature
    ├── predicate hypothesis
    ├── raw surfaces
    ├── signal refs
    ├── evidence
    └── temporal hypotheses
    │
    ▼
ENTITY RESOLUTION
    │
    ▼
SEMANTIC REGIME
    │
    ▼
CLAIM MATERIAL
    │
    ▼
VALIDATION
    │
    ▼
ADMISSION
    │
    ▼
RELATION CLAIM
    │
    ├──────────────► GRAPH EDGE
    │
    ├──────────────► HYPEREDGE
    │
    └──────────────► WORLDLINE
```

---

# 102. THE THREE SEMANTIC LAYERS

Make this distinction explicit in code/docs:

## Layer 1 — Observation

```text
RelationSignal
```

Meaning:

> something relational-looking was observed.

## Layer 2 — Hypothesis

```text
RelationCandidate
```

Meaning:

> given these observations, this relational configuration is a candidate interpretation.

## Layer 3 — World assertion

```text
RelationClaim
```

Meaning:

> the platform admitted this assertion under an explicit semantic/validation contract.

The graph:

```text
GraphEdge
```

is a projection of Layer 3.

That distinction is non-negotiable.

---

# 103. DO NOT CREATE A FOURTH EPISTEMIC LEVEL

Do not end up with:

```text
Signal
Hypothesis
Candidate
Interpretation
Assertion
Claim
Edge
```

all meaning almost the same thing.

Use:

```text
Signal
Candidate
Claim
Edge
```

as the main relation hierarchy.

Use nested/value objects for:

```text
PredicateHypothesis
PredicateSignature
TemporalHypothesis
RelationParticipant
```

where necessary.

---

# 104. ENTITY TYPES VS RELATION TYPES — FINAL POLICY

### Entity types

It is acceptable and useful to have:

```text
core:Person
core:Organization
core:WebSite
...
```

because they provide:

```text
coarse semantic affordances
blocking
typing
query expansion
interpretation
```

and the type space can grow modularly.

### Relation types

Do not require:

```text
all relations fit a finite global edge list
```

because relations are much more dependent on:

```text
context
source vocabulary
language
document structure
task
semantic regime
temporal frame
event structure
```

The relational space therefore begins as:

```text
observed structure
```

and only later becomes:

```text
known predicate
```

when the semantic system earns that mapping.

---

# 105. EXTERNAL VOCABULARY POLICY

Schema.org/Wikidata/SKOS/other ontologies are:

```text
semantic instruments
```

not:

```text
platform reality
```

Use them for:

```text
mapping
labels
hierarchies
aliases
blocking hints
query expansion
interop
```

not:

```text
global truth
```

The current SKOS model is explicitly designed around concept schemes, labels, hierarchies and mappings, while schema.org itself treats types and properties as an evolving vocabulary rather than a universal mandatory constraint system.

---

# 106. PERFORMANCE TARGET

The extraction layer must remain linear or bounded-superlinear within named local structures.

For every producer report:

```text
input size
signals produced
pairs considered
structural nodes considered
time
```

Do not optimize prematurely with distributed infrastructure.

The immediate objective is:

```text
correct substrate
```

not:

```text
Kafka everything
```

.

Optimization comes after the semantic contract is correct.

---

# 107. TEST BASELINE

Do not introduce regressions into:

```text
projection
acquisition
interpretation
admission
control-plane
shared
```

Existing known failures must remain unchanged unless directly affected.

Track:

```text
baseline membership
new failures
fixed failures
new tests
```

Never report:

```text
green
```

when there are new failures hidden among known ones.

---

# 108. ACCEPTANCE CRITERIA

Feature 021 is complete only when ALL are true.

## Entity substrate

* foundational atomic vocabulary exists
* entity/value types are distinct
* type hypotheses are first-class
* type assertions remain durable
* multiple type hypotheses are preserved
* unknown types are preserved
* external mappings are explicit
* ontology never gates extraction
* mention/entity separation preserved

## Relation substrate

* RelationSignal has explicit structural contract
* mandatory signal kinds exist
* real mention references are used
* n-ary relation is native
* polarity is explicit
* predicate signature exists
* raw surface is evidence, not logical identity
* active/passive can share logical identity
* multiple producers can corroborate one candidate
* distinct relations on same endpoints do not merge
* semantic conflicts do not use majority vote
* unknown predicates survive
* alternatives survive
* no producer emits claim/edge

## Lifecycle

* Candidate exists before material
* Material exists before validation
* Validation exists before admission
* RelationClaim exists only after admission
* GraphEdge exists only after RelationClaim

## Persistence

* signals persist
* candidates persist
* predicate hypotheses are reconstructible
* temporal observations persist
* round-trip works
* replay works

## Projection

* direction preserved
* n-ary preserved
* attributes distinguished from entity-to-entity edges
* edge points back to claim
* graph remains rebuildable

## Determinism

* two independent runs identical
* order of producers does not alter IDs
* no clock dependency
* no random dependency
* no dict-order dependency

## Boundedness

* no O(N²) global mention sweep
* every producer names neighbourhood
* hard ceilings are machine checked
* cost metrics are reported

---

# 109. FINAL GOLDEN EXAMPLES

The final implementation MUST be able to represent at least these cases correctly.

## Case A — known relation

```text
John Smith works for Acme Corporation.
```

Result:

```text
mentions:
    John Smith
    Acme Corporation

type hypotheses:
    Person
    Organization

relation signal:
    predicate_surface = "works for"
    predicate_signature = works_for(...)
    relation_ref = works_for

candidate:
    CAND-...

resolution:
    John → ENT-X
    Acme → ENT-Y

claim:
    ENT-X works_for ENT-Y

edge:
    ENT-X → works_for → ENT-Y
```

---

## Case B — active/passive

```text
John acquired Acme.
```

versus:

```text
Acme was acquired by John.
```

Result:

```text
same logical relation configuration
different surface evidence
different signal ids
same logical candidate identity
```

---

## Case C — unknown relation

```text
John is the originator of Acme.
```

Result:

```text
signal ✅
candidate ✅
predicate surface ✅
predicate signature ✅
relation_ref = None
state = UNKNOWN
claim = not yet
graph edge = no
```

No information loss.

---

## Case D — event

```text
John sold Acme to Microsoft in 2020.
```

Result:

```text
NARY candidate
seller = John
asset = Acme
buyer = Microsoft
time = 2020
```

No binary collapse.

---

## Case E — structural

```html
<a href="https://example.com/acme">Acme</a>
```

Result:

```text
LINK signal
```

not:

```text
cites
owns
hosts
employs
```

---

## Case F — table

```text
CEO          Company
John Smith   Acme
```

Result:

```text
TABLE signal
CEO = observed role/header
John Smith = participant
Acme = participant
```

Semantic relation may remain unknown.

---

## Case G — conflicting interpretations

```text
same participant pair
same predicate surface
semantic regime A → works_for
semantic regime B → affiliation
```

Result:

```text
one logical hypothesis
multiple predicate readings
state = AMBIGUOUS or CONFLICTING
nothing overwritten
```

---

## Case H — negative

```text
John did not acquire Acme.
```

Result:

```text
predicate = acquire
polarity = denied
```

No positive acquisition claim is generated merely because the verb appeared.

---

# 110. DEVELOPMENT ORDER

Do not randomly interleave changes.

Execute in this order:

```text
PHASE 1
identity/domain contract cleanup

PHASE 2
atomic entity type vocabulary

PHASE 3
type hypothesis + mention binding

PHASE 4
RelationSignal structural contract

PHASE 5
predicate signature + candidate identity correction

PHASE 6
producer corrections

PHASE 7
assembly / conflict semantics

PHASE 8
real execution lifecycle

PHASE 9
durable persistence + replay

PHASE 10
graph projection verification

PHASE 11
golden corpus + mutation tests

PHASE 12
benchmark + regression
```

Do not start by adding dozens of extraction rules.

First make the substrate correct.

---

# 111. STOP CONDITIONS

Stop and report explicitly rather than inventing a semantic answer if you encounter:

```text
a new ontology requirement
a relation identity ambiguity
an external vocabulary mapping ambiguity
an entity/value ambiguity
a parser capability that cannot be made deterministic
a persistence representation that loses information
```

Use an explicit:

```text
UNKNOWN
AMBIGUOUS
CONFLICTING
UNSUPPORTED
```

state where appropriate.

Do not turn uncertainty into a guessed type/relation merely to make the pipeline green.

---

# 112. FINAL DESIGN STATEMENT

The resulting system should conceptually answer five different questions:

```text
1. WHAT WAS OBSERVED?
```

via:

```text
Observation / Mention / RelationSignal
```

```text
2. WHAT COULD IT BE?
```

via:

```text
TypeHypothesis / PredicateHypothesis / RelationCandidate
```

```text
3. WHAT DOES OUR SEMANTIC REGIME CALL IT?
```

via:

```text
TypeAssertion / RelationRef / mapping
```

```text
4. WHAT SURVIVED VALIDATION AND ADMISSION?
```

via:

```text
RelationClaim
```

```text
5. WHAT GRAPH VIEW DO WE PROJECT?
```

via:

```text
GraphEdge / HyperEdge
```

Never collapse those five questions into one object.

---

# 113. MOST IMPORTANT PHILOSOPHICAL REQUIREMENT

Do not optimize the system toward:

> "find all edges."

Optimize it toward:

> "observe all recoverable relational structure, preserve its uncertainty, construct competing interpretations, resolve participants and semantics explicitly, admit only what the platform has earned, and project graph state from admitted world claims."

That is the architecture.

The universal part is NOT:

```text
universal ontology
```

and NOT:

```text
universal relation enum
```

.

The universal part is:

```text
UNIVERSAL OBSERVATION LANGUAGE
```

for heterogeneous relational evidence.

The final abstraction is:

```text
                 ┌──────── lexical ────────┐
                 ├──────── syntactic ──────┤
                 ├──────── structural ─────┤
                 ├──────── hyperlink ──────┤
                 ├──────── table ──────────┤
                 ├──────── list ───────────┤
                 ├──────── metadata ───────┤
OBSERVATION ─────┼──────── event ──────────┼────► RelationSignal
                 ├──────── temporal ───────┤
                 ├──────── attribute ──────┤
                 ├──────── reference ──────┤
                 ├──────── cooccurrence ───┤
                 └──────── semantic ───────┘
                                      │
                                      ▼
                             RelationCandidate
                                      │
                                      ▼
                           Predicate/Entity Resolution
                                      │
                                      ▼
                               Claim Material
                                      │
                                      ▼
                                  Validation
                                      │
                                      ▼
                                  Admission
                                      │
                                      ▼
                               RelationClaim
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                    GraphEdge                 HyperEdge
                         │                         │
                         └────────────┬────────────┘
                                      ▼
                                  Worldline
```

And independently:

```text
                    ┌─ Person
                    ├─ Organization
                    ├─ WebSite
                    ├─ WebPage
                    ├─ Place
                    ├─ Document
                    ├─ Product
                    ├─ Service
                    ├─ Event
                    ├─ Software
                    └─ ...
Mention ───────────► TypeHypothesis ───► TypeAssertion
```

The first branch is **open-world relational structure**.

The second branch is **bounded foundational type semantics**.

They intersect through:

```text
role hints
blocking
semantic regimes
mapping
validation
```

but neither branch is allowed to become the other's ontology.

---

# 114. DELIVERABLES

At completion provide:

1. changed-file manifest,
2. architecture summary,
3. domain model changes,
4. migration summary,
5. producer summary,
6. identity changes,
7. execution path before/after,
8. graph projection semantics,
9. corpus coverage,
10. mutation-test results,
11. replay/determinism results,
12. benchmark results,
13. complete test matrix,
14. explicit remaining debt.

Do not claim "feature complete" merely because tests pass.

The final report must distinguish:

```text
implemented
verified
verified only offline
known limitation
deferred
```

The feature is complete only when the architecture above is actually represented in production code and the golden/mutation corpus proves the constitutional properties.
