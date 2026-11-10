# Relation extraction and source type observations

## Producer boundary

Relation extraction uses the existing RelationSignal / ProducerDeclaration contract. GLiNER
RelEx and Stanford OpenIE are optional producers; neither bypasses the registry, resolves a
mention, writes a candidate, creates a RelationClaim, or updates a graph projection.

A model-generated label such as works_for is not a quotation from the page. The producer
emits a signal only when it can locate the predicate between the two exact participant spans
in the original text. Otherwise it returns a machine-readable refusal in RelationProducerReport.
This deliberately trades recall for auditable evidence and avoids fabricating trigger spans.
GLiNER and OpenIE share one independence family: two algorithms reading the same captured
page are not two independent sources and must not inflate corroboration counts.

## GLiNER RelEx

GLiNER is optional and loaded lazily. Install the GLiNER package in a runtime image that
explicitly enables this producer, then configure the chosen checkpoint and labels. The
default checkpoint reference is knowledgator/gliner-relex-large-v1.0. Entity and relation
thresholds are explicit; relation threshold defaults to 0.65. The adapter refuses documents
over 12,000 characters and more than 1,024 possible entity pairs.

## Stanford OpenIE

Stanford OpenIE is invoked as a configured Java argv, never through shell=True. Operators
must install Stanford CoreNLP/OpenIE and configure the classpath. The CLI TSV contract is
confidence, subject, relation, object. The adapter enforces timeout, document and result
ceilings and exact source grounding.

Stanford OpenIE is GPL-licensed upstream. Deployments must review that licence before
redistributing the Java runtime or bundling it into a product image.

## TypeSignal

StructuredTypeSignalExtractor reads schema.org JSON-LD type statements and records
TypeSignal values against mentions already resolved by the caller's mention index. An
unresolved mention or source spelling that cannot be cited exactly produces a typed refusal.
OpenGraph og:type is recognized as page-level metadata but refused as a person TypeSignal:
og:type describes the retrieved page, not the person named by og:title. A document-level
Mention must exist before that metadata can be attached without guessing.
source_vocab is an external vocabulary reference or null; parser/model identity is kept in
producer_ref. TypeSignal identity does not include later mapping proposals or evidence-link
revisions. It is not a TypeAssertion.

RDFa, Microdata and general HTML metadata remain future adapters; they must implement the
same source-span / mention-index contract before they can be advertised as supported.

## Verification

Run uv sync --locked --all-packages --all-groups, then:

    .venv/bin/python -m pytest apps/interpretation/tests/test_ml_relation_producers.py apps/interpretation/tests/test_structured_type_extractor.py apps/shared/tests/unit/test_type_signal.py -q

The tests use deterministic fake inference and Java runners. They do not claim that model
weights or a CoreNLP installation were downloaded. A real deployment proof must provision the
selected model and Stanford runtime in its acceptance environment.

## Source-addressing edge cases

The structured adapter accepts only script elements whose declared media type is application/ld+json; ordinary JavaScript and unrelated script payloads are ignored. Every @type entry on one JSON-LD node is retained against that node's already-resolved mention, without consuming the same name locator twice. Name addressability is checked against the JSON name property itself, not an equal string in a description or another field.

Relation predicate grounding is token-bounded as well as source-located: a model label that matches only a substring inside a larger word is refused. Repeated predicate occurrences between participants remain ambiguous and are refused rather than selecting the first span.
