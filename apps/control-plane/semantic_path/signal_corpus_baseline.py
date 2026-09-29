"""The signal corpus as a recorded baseline (feature 019, T040).

T040 says *re-record expectations and read the diff before writing*. The diff is in
:mod:`this module`'s history and in the comment below; this file is the recorded side.

What changed when 019's signal layer entered the pipeline, and why every golden-path
``candidate_id`` moved:

* ``RelationCandidate.extraction_method`` is now ``orchestrated`` rather than
  ``lexical_pattern``. The old value described one producer; the reading is now assembled,
  and recording the old one would have been a false account of how the reading was made -
  in *identity material*, so the address would have been a lie too.
* ``RelationCandidate.signal_refs`` is new, and it is revision material, so it enters the
  address.
* ``RelationCandidate.extraction_rule_id`` is now the producer list rather than a single
  rule id, for the same reason.

Nothing about the *claims* changed: the corpus's ``relation_id`` values are stable, because
the identity split is exactly the separation that keeps a change to how a hypothesis was
formed from a change to what was concluded.

**Phase 4B re-recorded the signal layer, and the diff is in the comment below.** Every case
digest that touches a producer moved, and the two that do not - ``nary_event`` and
``triple_corroboration`` - are the two whose signals are hand-declared through
:func:`~semantic_path.signal_corpus._declared` with no producer output, which is the check
that the movement is the *producers'* and not the harness's. What moved and why:

* ``link`` - one signal per anchor rather than two. A ``LINK`` and a ``REFERENCE`` were
  emitted per anchor from the same two references and the same surface, so a page with three
  anchors was read as six and reported twice the corroboration in it (FR-034). The case's
  ``kinds`` went from two entries to one.
* ``table``, ``attribute_value``, ``document_hierarchy``, ``metadata`` - every participant is
  re-addressed. A ``header:``/``cell:``/``attribute:``/``document:current`` participant is gone
  (FR-094), and the values are now the document's own text at its own character offset rather
  than a lowercased namespace with a 64-character cut. A different mention reference is a
  different candidate, so these ids moved and had to.
* ``active_passive``, ``text_vs_table``, ``unknown_relation`` - hand-declared signals moved
  because :func:`_declared` now states a ``basis``, and a basis is in the address material.

The recorded corpus digest for 019's signal layer is below. It is a *baseline to compare
against*, not a constant to assert - a test that asserted it would fail on every legitimate
change and be deleted within a week.

**The mention-binding seam re-recorded the corpus, and the diff is the split proving itself.**
``RelationCandidate.assembly_state`` is new and is **revision** material, so it enters
``candidate_id`` and nothing enters ``logical_candidate_id``. Seven of the ten case digests moved
and **three did not**, and which three is the whole point:

* ``active_passive``, ``nary_event``, ``triple_corroboration`` are unchanged. Their verified
  payload is built from ``logical_candidate_id`` values, from reading *counts*, and from arity and
  role bindings - never from a ``candidate_id``.
* ``link``, ``table``, ``metadata``, ``attribute_value``, ``document_hierarchy``,
  ``text_vs_table`` and ``unknown_relation`` moved. Every one of them reports at least one
  ``candidate_id``.

So the recorded baseline is now a demonstration rather than a number: had ``assembly_state`` been
placed in the *logical* material, those three would have moved with the other seven and the
platform would hold two ``logical_candidate_id`` values for one participant configuration read two
ways - which is exactly the fork ``ARBITRATION`` §3 forbids and the one that made a structural
disagreement indistinguishable from a different hypothesis. The other change in this wave is not
visible here at all: the deferred occurrence addresses a producer emits are unchanged, so no
producer-side reference moved.

**Phase 4C re-recorded the corpus twice, and the diff is the answer to "was the deletion a
redundancy?".** C1 (``SignalKind``) moved **nothing at all** - every one of the ten case digests
is byte-identical. That is the result, not an absence of one: no producer declared, emitted or
keyed on ``NEGATION``/``QUANTITY``/``COREFERENCE`` (the measurement is in
``apps/interpretation/tests/test_signal_kind_channels.py``), and a case's digest is taken over
``signal_ids``/``kinds``/``candidate_id``/``logical_candidate_id``/``groups``/``complete`` and the
payload its own assertions ran over - none of which reads the enum's *membership*. Deleting three
members a corpus never touched could not move a corpus, and had it moved one, that would have been
the finding.

C2 (role slots as the fourth structural axis) moved **exactly one** case, ``nary_event``, and the
other nine are unchanged - including every producer case. The reason is the reason the axis is
built the way it is: a sixth ``reading_key`` component is ``""`` for every signal in the corpus
because **no corpus case has two producers disagreeing about role slots**, so the component is
inert and the keys are unchanged. ``nary_event`` moved because its *expectation* now also runs the
partial-set disagreement - one producer naming two of three slots against another naming all three
- and reports the two ``CONFLICTING`` readings, the ``[2, 3]`` role counts and the
``role_slots`` axis in its verified payload. The subject of that case has always been "a full set
of role bindings survives assembly"; a partial set over the same configuration is the same
question asked the other way, so it belongs there rather than in a new eleventh case that would
have changed the corpus's shape as well as its digest.

**The occurrence-address encoding changed, and this baseline is now stale on purpose.** The
recorded digests below were taken under the retired address grammar
``surface[:@<start>-<end>:]<label>:<surface>``, whose label was the text up to the *first* ``:`` -
so a syntactic producer's dependency-arc labels (``nmod:of``, ``nsubj:pass``) made one string the
address of two different occurrences, and the platform could not tell that misparse from a surface
that genuinely contains a colon. The grammar is now injective by construction
(:func:`domain.mention_occurrence_index.mint_occurrence_address`: the fields are the platform's own
``canonical_material`` and the address carries that material's ``digest128``), so **every deferred
address a producer emits is a different string** and so is every ``signal_id`` derived from one.

**The constants are deliberately left as they are.** Re-recording is an act with the diff read
first (T040), and a silent overwrite would have been the wrong kind of quiet: it would destroy the
only record of what the corpus looked like *before* the fix, which is the side of the diff a reader
needs. Nothing asserts these numbers - the file says so itself, and the reasoning still holds: a
test that asserted them would fail on every legitimate change and be deleted within a week. So the
measurement now, for whoever re-records:

* **Five cases moved** - ``attribute_value``, ``document_hierarchy``, ``link``, ``metadata`` and
  ``table``. All five are producer cases, and all five report at least one ``candidate_id``, which
  is minted from ``(subject_mention_ref, object_mention_ref)`` - and a bound ``MN-`` comes from a
  key built out of the address's own fields.
* **Five did not** - ``active_passive``, ``nary_event``, ``text_vs_table``, ``triple_corroboration``
  and ``unknown_relation``. Three of those are hand-declared through
  :func:`~semantic_path.signal_corpus._declared` with no producer output; the other two verify
  their payload from ``logical_candidate_id`` values, reading counts and arity. The split is the
  same demonstration the 4C re-record made, for the same reason: the change is the *producers'* and
  not the harness's.
* ``RECORDED_CORPUS_DIGEST`` is now ``455205a4413984cbc5c5c61ac066ad48``.

**What did *not* move is worth stating too, because it is the point of requirement five.** A
corpus or a store written under the retired grammar does not decode into the wrong pair: it is
refused with ``mention_address_unreadable``, whose message names the retired form. So nothing was
migrated, because there is nothing here to migrate - the recorded numbers are a *record* of a past
state, and a past state is exactly what they are for.

**The one thing the C2 mutation found that the digest cannot show.** Restoring the pre-4C
``_roles_of`` did not produce "one candidate with no roles" - it produced a *failed batch*.
``RelationCandidate`` refuses a ``NARY`` candidate with fewer than two role assignments
(``insufficient_role_assignments``), so swallowing the partial set handed it a ``nary`` reading
with nothing in ``role_assignments`` and the whole assembly raised. One producer naming two of
three slots took every other signal on the pair down with it, and the error a caller saw named
role assignments rather than the producer or the pair. ``test_restoring_the_role_slot_unanimity_
rule_fails_this_file`` asserts that shape by name, because a guard written against a wrong
picture of the old behaviour guards nothing.
"""

from __future__ import annotations

#: The signal corpus digest recorded after Phase 4C's two re-records (``SignalKind`` cleanup and
#: the role-slot axis). Change it deliberately, with the diff read first — the diff is in this
#: module's docstring, and the C1/C2 diffs are the two that matter: **zero** cases moved for the
#: enum deletions and **one** (``nary_event``) moved for the new axis.
RECORDED_CORPUS_DIGEST = "09bd45cfc801beac46318d7bfb69394a"

#: Per-case digests, so a diff can say *which* case moved rather than only that one did.
RECORDED_CASE_DIGESTS: dict[str, str] = {
    "active_passive": "83fdc1748a6918b5a254da0453c3d09a",
    "nary_event": "664d0c083256007ac3faf9fb7616f725",
    "unknown_relation": "18b7fff4e28c2d45758ff969eb810a9b",
    "link": "7bde99c63cd78f95c513fcd636bb62eb",
    "table": "6c3dfb9c31b54a5519a63b4091a7c37a",
    "metadata": "8207344c0b3516675612ddaf5901745f",
    "text_vs_table": "b71b811484a0ade8a827e41fc1fdd134",
    "triple_corroboration": "f7fc6e6b07af6d8a0bf8425d29de7980",
    "attribute_value": "b60f517558d4f1bf7efc7c8fa5c32751",
    "document_hierarchy": "b12c2093875843ed835712ac0484f80b",
}


#: The golden corpus is unchanged in case count: 18, ten worldline and eight named
#: refusals, with 8 graded situations. Its digest moved with the candidate ids above; its
#: *shape* did not.
RECORDED_GOLDEN_CASE_COUNT = 18
