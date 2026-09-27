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

The recorded corpus digest for 019's signal layer is below. It is a *baseline to compare
against*, not a constant to assert - a test that asserted it would fail on every legitimate
change and be deleted within a week.
"""

from __future__ import annotations

#: The signal corpus digest recorded when 019 was completed. Change it deliberately, with
#: the diff read first.
RECORDED_CORPUS_DIGEST = "802e8ce88d7307bc0de203d1f827e086"

#: Per-case digests, so a diff can say *which* case moved rather than only that one did.
RECORDED_CASE_DIGESTS: dict[str, str] = {
    "active_passive": "abe4ece05e135adb",
    "nary_event": "9b58103da4fa5197",
    "unknown_relation": "a9b859de15dc49a7",
    "link": "6a054275043012e9",
    "table": "b41e16a55d0bbe5f",
    "metadata": "7e422bfc39bfd4de",
    "text_vs_table": "2b967b91fb5537b9",
    "triple_corroboration": "f7fc6e6b07af6d8a",
    "attribute_value": "305b72466c507d6b",
    "document_hierarchy": "1b615fabbfd741f9",
}

#: The golden corpus is unchanged in case count: 18, ten worldline and eight named
#: refusals, with 8 graded situations. Its digest moved with the candidate ids above; its
#: *shape* did not.
RECORDED_GOLDEN_CASE_COUNT = 18
