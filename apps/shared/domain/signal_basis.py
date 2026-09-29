"""The observational basis: **why** a producer says it saw a connection.

Feature 021, brief §16 (``input.md:1111-1137``); spec FR-014; ``data-model.md`` part 6.2;
``repair/A7-migration-021.md`` D2.2; ``repair/ARBITRATION.md`` §6.

**This is the field that replaced an invariant nobody could satisfy honestly.** The old rule
was ``relation_surface != '' OR relation_ref != NULL``, and its only enforcement on the domain
side was ``signal_asserts_nothing``: a signal with no predicate words and no operator was
refused. That rule looks like a floor and is actually a ceiling, and it forbids the one
observation a co-mention producer legitimately makes. ``John Smith`` and ``Acme Corporation``
appearing in one sentence is an observation. It is not a claim that they are related, it is not
a claim that they are *not* related, and it is not a gap - the producer looked, saw adjacency,
and declined to name it. Requiring a surface forced one of three bad answers: invent a word,
mint a ``related_to`` edge the document never stated, or drop the observation and lose the fact
that the two mentions were near each other. The third is the one that happens, and it is the
worst: an unrecorded adjacency and an unexamined one are indistinguishable afterwards.

So brief §16 says to remove the invariant "when it makes CO_OCCURRENCE structurally impossible"
and replace it with a positive requirement: **every signal must have an explicit observational
basis**. That is a strictly better-shaped rule. It cannot be satisfied by silence, because
silence has no basis; and it is satisfiable by the honest observation, because a co-mention
genuinely has a basis - proximity - and saying so is exactly what happened.

**Why a closed enumeration and not a free string.** A basis is the answer to "how do you know?",
so a basis nobody can enumerate is a basis nobody can audit. Nine members, taken verbatim from
the brief and never extended casually: a new way of observing is a *capability* change, and it
is reviewed as one, on the same grounds as a new :class:`~extractors.signals.signal.SignalKind`.
The strings are the brief's own words hyphenated into column values, because
``repair/A7-migration-021.md`` D2.3 pins them in SQL as literals and a stored row has to match.

**The one narrowing that is not merely a rename.**
:attr:`SignalBasis.PREDICATE_TEXT` is the only basis that *obliges* a surface, and the obligation
is arithmetic rather than stylistic: a producer that says "I read the words" and supplies no
words has not read the words. Every other basis - proximity, a table slot, a hyperlink, a
citation, a metadata field, an event frame, an attribute key, a DOM relation - can be observed
with no predicate words at all, and refusing those would re-create the invariant this field
exists to replace. So :attr:`SIGNAL_BASES_REQUIRING_PREDICATE_WORDS` names the one, and the
signal contract consults it rather than re-deriving the rule.
"""

from __future__ import annotations

from enum import StrEnum

#: The longest member token, ``predicate_text`` / ``metadata_field`` at 14 characters.
#: Published because migration ``021`` sizes ``relation_signal.observational_basis`` as
#: ``String(24)`` from this number (``repair/A7-migration-021.md`` D1.3), and a column too
#: narrow for its own vocabulary is a truncation nobody would notice until a row was refused.
MAX_BASIS_TOKEN_LENGTH = 24


class SignalBasis(StrEnum):
    """How this producer saw the connection - a closed vocabulary of nine (FR-014).

    The brief's list, verbatim, from ``input.md:1125-1137``::

        predicate text
        DOM relation
        table slot
        hyperlink
        citation
        proximity
        metadata field
        event frame
        attribute key

    and, as the column values migration ``021`` stores, hyphenated to snake_case
    (``repair/A7-migration-021.md`` D2.3). The two lists are the same nine observations; only
    the spelling differs, and the spelling that reaches a database is the one written out here.

    Read the members as *answers to "how do you know?"*, and the set falls out rather than
    being an arbitrary enumeration of nine:

    - :attr:`PREDICATE_TEXT` - words between the participants. The common case, and the only
      one that requires a :attr:`RelationSignal.relation_surface`: a producer that declares
      this basis and supplies no words has claimed an observation it did not make.
    - :attr:`DOM_RELATION` - the structure of a document. One node's containment, ordering or
      reference to another's, as a parse of the markup rather than a reading of the prose.
    - :attr:`TABLE_SLOT` - a header naming one end and a cell supplying the other. ``Role`` |
      ``CTO`` is a relation stated by position in a grid, and there is no phrase in the cell.
    - :attr:`HYPERLINK` - an anchor and its target. The words are the anchor text and they
      describe the link, not the relation, so they cannot be the basis.
    - :attr:`CITATION` - a reference: a footnote marker, a citation, a ``see also``. The
      named thing is the relation; the marker is the evidence.
    - :attr:`PROXIMITY` - two mentions in one sentence, window or block, with nothing between
      them. **The basis that makes a surface-less signal legal and honest**, and the member
      this whole field was written for: the observation is real, the naming is absent, and the
      record says so in the one field that can carry it.
    - :attr:`METADATA_FIELD` - a field the document states about itself: author, publisher,
      parent, path, domain.
    - :attr:`EVENT_FRAME` - a parsed event structure: a predicate with argument positions.
      Distinct from :attr:`PREDICATE_TEXT` because the words alone are not the observation -
      the frame is - and a signature is minted from the frame while the surface stays evidence.
    - :attr:`ATTRIBUTE_KEY` - a key/value pair, as in ``Role: CTO`` or a YAML front-matter
      block. The key is the relation; the value is one end.

    **Unknown relation semantics are valid.** The brief says so in the same breath
    (``input.md:1139``), and it is why this is a basis rather than a relation type: the
    platform's inability to name ``John Smith`` and ``Acme Corporation`` as related is a fact
    about the platform's vocabulary, and a signal may record an observation the vocabulary
    cannot yet express.
    """

    PREDICATE_TEXT = "predicate_text"
    DOM_RELATION = "dom_relation"
    TABLE_SLOT = "table_slot"
    HYPERLINK = "hyperlink"
    CITATION = "citation"
    PROXIMITY = "proximity"
    METADATA_FIELD = "metadata_field"
    EVENT_FRAME = "event_frame"
    ATTRIBUTE_KEY = "attribute_key"


#: Every basis, in declaration order. For refusals that must list the vocabulary, for the
#: corpus (how many signals rest on proximity, and how many on words nobody typed), and for
#: the test that pins the set to the brief's nine.
SIGNAL_BASES: tuple[SignalBasis, ...] = tuple(SignalBasis)

#: The one basis that obliges a predicate surface. See the module docstring for why the other
#: eight do not, and :mod:`extractors.signals.signal` for the refusal that consults this.
SIGNAL_BASES_REQUIRING_PREDICATE_WORDS: frozenset[SignalBasis] = frozenset(
    {SignalBasis.PREDICATE_TEXT}
)

#: The bases whose observation is a structure with no predicate words, grouped because the
#: corpus answer that matters is "how much of what we found can we even name", and that is
#: counted over this set. It is a view over :data:`SIGNAL_BASES`, not a second enumeration, so
#: a tenth basis cannot join one and not the other.
SURFACELESS_SIGNAL_BASES: frozenset[SignalBasis] = frozenset(SIGNAL_BASES) - (
    SIGNAL_BASES_REQUIRING_PREDICATE_WORDS
)

#: Stable order for any consumer that has to serialise the enumeration - a migration's
#: whitelist, a corpus report, a docstring. Declaration order, never ``set`` iteration order,
#: because a value that changes between processes is not a vocabulary.
SIGNAL_BASIS_TOKENS: tuple[str, ...] = tuple(basis.value for basis in SIGNAL_BASES)


__all__ = [
    "MAX_BASIS_TOKEN_LENGTH",
    "SIGNAL_BASES",
    "SIGNAL_BASIS_TOKENS",
    "SIGNAL_BASES_REQUIRING_PREDICATE_WORDS",
    "SURFACELESS_SIGNAL_BASES",
    "SignalBasis",
]
