"""The stage between parsed payload records and typed, related mentions.

Feature 021 brief §16 (how do you know?), §25 (a producer below mention extraction), §26
(:mod:`domain.mention_occurrence_index` is the mention seam), §31 (structural observation read *as
structure*); spec FR-008, FR-009, FR-014, FR-016…FR-019, FR-041…FR-043; ``ARBITRATION`` §8;
constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**The seam this package fills.** The chain, end to end, with this package in the middle:

.. code-block:: text

    source → CapturePage(raw bytes) → observation.created (Kafka)
           → parsers.payload      → ObservedField records
           → extractors.payload   ← HERE: typed mentions and related pairs
           → 021 substrate        → candidates, claims, admission

:mod:`parsers.payload` states what a payload **says** — one record per value, with its value type,
its byte span, its depth, a closed position label, and either a deferred occurrence address or the
named reason there is none. It is below mention extraction on purpose: it resolves nothing, filters
nothing, and decides no type.

This package is the first stage above it allowed to make a **judgement**, which is exactly why it
is the stage most able to lie. Four judgements, and each is confined to a module whose refusals are
as loud as its output:

:mod:`~extractors.payload.keytable`
    Which key names may suggest a type, as a **declared, versioned, inspectable table** whose only
    match is equality on a whole key segment. A key nobody has a rule for yields **no hypothesis**,
    recorded as ``key_rule_absent``. A substring match is a guess and there is no branch that could
    perform one. Numbers get no numeric-semantic hypothesis without a schema the source published.
:mod:`~extractors.payload.hypotheses`
    The hypotheses, each carrying a :class:`HypothesisCitation` that names the key path segment
    that suggested it and **which epistemic level** proposed it — a word, or a source-published
    schema — and each naming its own confidence. No hypothesis may be emitted with the inherited
    ``1.0`` of :attr:`semantic.blocking.TypeHypothesis.confidence`, and the table refuses a row that
    would let one through.
:mod:`~extractors.payload.structure`
    The relations, from structure: ``ATTRIBUTE_KEY`` for an object member, ``DOM_RELATION`` for an
    array element, both with the operator (``relation_ref``) **unset** because a JSON document
    contains no verbs. Every participant is a **resolved** ``MN-``; an end that cannot be resolved
    is excluded and counted, and truncation propagates all the way into the signal address.
:data:`~extractors.payload.keytable.DEFAULT_DECLARED_SCHEMAS`
    Empty, and pinned by a test: the platform publishes no source schema, so the schema level is
    reachable only by a caller who has been handed one.

**What this package will not do, as a list, because each is a temptation.** It mints no entity id:
participants are mentions. It resolves nothing — a mention id is a mention id, and saying two are
the same thing is a decision with a :class:`ResolutionDecisionRecord` behind it, which this stage
has no business producing. It imports no graph, claim, admission, projection or resolution symbol,
and a test reads the AST of every module here to keep that true. It does not filter: a field
nobody anticipated is emitted, refused by name where a name applies, because a producer that
decides which observations are interesting has begun deciding what the source said. And it writes
no ``confidence`` it did not measure: the type-hypothesis numbers are **declared constants in a
versioned table**, published as declarations precisely because nothing here measures them.

**Determinism is structural, not a convention (constitution VI, Domain Invariant 12).** No clock, no
randomness, no ``set`` iteration and no dict-order dependence on any path from a record to a
signal. One pass over ``payload.records`` in document order, one container end resolved per
container and shared, every tuple built by appending in that order, every ``to_dict`` in declared
field order, and :attr:`extractors.signals.signal.RelationSignal.signal_id` content-addressed by the
signal contract itself. Two processes handed one payload and one scope produce the same signals in
the same order with the same ids — which is the property that makes an ``MN-`` usable as a join key
at all, and the reason the cross-process test pins ``PYTHONHASHSEED`` differently in each child.

**The name is deliberately adjacent to** :mod:`parsers.payload`. The two are the two halves of one
chain, and a stack trace that names both is a stack trace that says where in the chain it broke.
"""
