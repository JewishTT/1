"""The table and list producers: a document's own tabular structure, as it stands.

Feature 019, T028 (FR-028, FR-047, FR-095, SC-F).

A table is a statement the document makes about itself, and it is usually the most explicit
statement in the whole artefact. ``| Name | Role |`` with ``| Jane Doe | CEO |`` says that
Jane Doe's role is CEO, in a structure designed to be unambiguous - and the platform
usually cannot use that, because ``CEO`` is not an operator in its vocabulary and the
column header supplies no verb to read a relation out of.

**So this producer reports the header, and refuses to interpret it.** It emits
``relation_surface="CEO"`` with :attr:`~extractors.signals.signal.RelationSignal.relation_ref`
left ``None``, which is FR-028 exactly: the table's own words reach the substrate intact
and a later ``SemanticRegime`` decides what ``CEO`` means. Emitting ``works_for`` here
would be a different and much worse producer - one that has silently acquired a
vocabulary, and whose output could not be re-derived from the table if the vocabulary
changed.

**Why the header, and not the value, is the surface.** The relation is *about* the column:
every cell in the ``Role`` column is in a role, and the header is what makes that true. The
cell is the participant. Putting the cell in the surface would produce one signal per cell
all carrying ``Jane Doe``, which says nothing about how the cells relate - and would make
FR-034's independence count count rows rather than observations.

**Two tables, one producer, two kinds.** :class:`TableExtractor` reads ``<table>`` markup
and emits :attr:`~extractors.signals.signal.SignalKind.TABLE`;
:class:`ListExtractor` reads a definition list and emits ``LIST``. They share this module
because they share the shape that matters - a key, a value, and no verb - and splitting
them would duplicate the reasoning about what a key means and does not mean.

**Nothing is dropped in silence, and that is Phase 4B's other half.** Three losses were
silent here and all three are now reported rather than papered over:

* a ``<dt>`` with no ``<dd>`` beneath it, which ``zip(..., strict=False)`` dropped on the
  floor, is emitted as a **term with no definition** and named as such. A term the document
  wrote and the pairing threw away is a field the producer read and could not complete, and
  losing it made a definition list with an odd number of entries look like a well-formed one.
* a data row whose width does not match the header's is still **not mispaired** - pairing it
  by position would attach a value to a column the markup never put it in, which is a
  falsehood about the document's own structure - but it is now **counted and reported** on
  every signal from that table, in ``Neighbourhood.notes`` and in
  ``extra["ragged_row_indexes"]``. Skipping is a decision; skipping *without a trace* is how
  three cells of a real table go missing (FR-095).
* the header row is chosen by a **heuristic** - the row with the most ``<th>`` cells - and
  ``precision`` used to open with ``exact``, which made a heuristic read as an exact reading
  and made :attr:`~extractors.signals.signal.Neighbourhood.is_exhaustive` a substring test
  over a sentence. It now says what it is.

**What it will not do.** It does not know which column is the key. A table's first column
*usually* is, and this producer does not care: it reads the header of every column and
emits a signal for each, with
:attr:`~extractors.signals.signal.DirectionHypothesis.AMBIGUOUS` because a header says what
kind of thing a column holds and not which end of the relation it is. It also does not
know whether two cells in one column are in a relation with each other - ``Alice, Bob`` in
a ``Name`` column may be one multi-valued cell or two rows, and the markup distinguishes
them and this producer deliberately does not guess which reading to record.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.mentions import deferred_occurrence
from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)

PRODUCER_REF = "structural/table"
LIST_PRODUCER_REF = "structural/list"
PRODUCER_VERSION = "2"
INDEPENDENCE_FAMILY = "markup"

#: One table's headers and cells. Small, and stated: a producer scoped to one table reads
#: one table, so a document with 200 tables is 200 calls and never one call that ranked
#: 40,000 cells.
MAX_PAIRS_CONSIDERED = 1024

#: The two ends' labels, from the markup that declares the positions. Before Phase 4B they
#: were ``header:`` and ``cell:`` - a *column label* and a *cell value* handed over as
#: mentions, which put the word "Role" in the world where a person was expected.
HEADER_LABEL = "th_text"
CELL_LABEL = "td_text"
TERM_LABEL = "dt_text"
DEFINITION_LABEL = "dd_text"

#: The `precision` a heuristic reading is published under, and the substring the
#: :attr:`~extractors.signals.signal.Neighbourhood.is_exhaustive` test is fixed against. Named
#: rather than written twice, and deliberately **not** starting with ``exact``: the old string
#: was ``"exact; header row chosen by most <th> cells (a heuristic)"``, which called a
#: heuristic exact and put the word "exact" in front of the admission that it was not.
PRECISION_HEURISTIC = "heuristic"
PRECISION_EXACT = "exact"


_CELL = re.compile(r"<t[hd]\b[^>]*>(?P<text>(?:(?!</t[hd]>).)*)</t[hd]\s*>", re.IGNORECASE | re.DOTALL)
_ROW = re.compile(r"<tr\b[^>]*>(?P<cells>(?:(?!</tr>).)*)</tr\s*>", re.IGNORECASE | re.DOTALL)
_TABLE = re.compile(
    r"<table\b[^>]*>(?P<rows>(?:(?!</table>).)*)</table\s*>", re.IGNORECASE | re.DOTALL
)
_LIST = re.compile(
    r"<dl\b[^>]*>(?P<items>(?:(?!</dl>).)*)</dl\s*>", re.IGNORECASE | re.DOTALL
)
_DT = re.compile(r"<dt\b[^>]*>(?P<text>(?:(?!</dt>).)*)</dt\s*>", re.IGNORECASE | re.DOTALL)
_DD = re.compile(r"<dd\b[^>]*>(?P<text>(?:(?!</dd>).)*)</dd\s*>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")

#: A header with no words names nothing, and a cell with no words is an empty cell. Neither
#: is a relation, and reporting one would be a signal whose surface is a space.
_EMPTY = frozenset({"", "&nbsp;", "-", "--", "n/a", "na", "tbd", "?", "unknown"})


def cell_text(fragment: str) -> str:
    """A cell's or term's visible text, tags stripped and whitespace collapsed."""
    return " ".join(_TAG.sub(" ", fragment).split())


def is_empty(text: str) -> bool:
    """Whether a cell carries no value worth reporting.

    ``&nbsp;`` is included because it is what a spreadsheet export puts in an empty cell,
    and a signal whose surface is a non-breaking space is a signal that looks like data and
    is not.
    """
    return text.strip().lower() in _EMPTY


#: One cell or term: its visible text and where it starts and ends, as
#: ``(text, char_start, char_end)``. A triple rather than a bare string because the position
#: is what makes the deferred address of a participant an *occurrence's* address - two cells
#: reading "Acme" in one table are two participants, and a producer reading one of them
#: twice is one observation. A pair was tried first and the missing end forced a guess at a
#: width, which is exactly the kind of inference a deferred address must not contain.
_Cell = tuple[str, int, int]


@dataclass(frozen=True, slots=True)
class _RaggedRow:
    """A data row whose width does not match the header's, reported rather than paired.

    The row is **not** mispaired - that decision is unchanged and is the right one - so the
    only thing this record adds is that the loss is countable. It carries the row's index,
    how many cells the header declared and how many the row carried, because "a row went
    missing" is not an answer a reader can act on and "row 1 of 3 columns carried 2 cells"
    is.
    """

    row_index: int
    declared_cells: int
    carried_cells: int

    def describe(self) -> str:
        return (
            f"row {self.row_index} carried {self.carried_cells} cell"
            f"{'' if self.carried_cells == 1 else 's'} where the header declared "
            f"{self.declared_cells}; it was NOT paired, because pairing it positionally "
            f"would attach a value to a column the markup never put it in"
        )


class TableExtractor:
    """HTML tables, as TABLE signals: one per non-empty cell, keyed on its column header.

    Scoped to one ``<table>``. A caller with a whole document splits it and calls
    :meth:`extract` per table, which keeps the neighbourhood honest - the extent a signal
    claims is the extent that was read.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.TABLE,),
            reads=(
                "one <table> element: the <th> cells of its header row, and every non-empty "
                "<td> cell beneath them. Each cell yields one signal whose surface is its "
                "column's header, because the header is what says what kind of thing the "
                "column holds - the cell is the participant, not the relation. Both "
                "participants are the header's and the cell's own visible text, addressed "
                "at their own character offsets, and the href/header/cell namespaces this "
                "producer used to mint are gone."
            ),
            cannot_read=(
                "which column is the key, and whether a column is single-valued. A table's "
                "first column usually is the key and this producer does not care: it reads "
                "every header and marks each signal's direction AMBIGUOUS, because a header "
                "says what a column holds and not which end of a relation it is. It also "
                "cannot tell one multi-valued cell from two rows, and does not guess. And it "
                "cannot tell whether a row of the wrong width was a merge, a spanning cell "
                "or a typo, so it reports the row and declines to pair it rather than "
                "choosing among the three."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None. 'CEO' is the document's word and the platform "
                "has no operator for it; emitting works_for here would be a producer that "
                "had quietly acquired a vocabulary, and its output could not be re-derived "
                "from the table if that vocabulary changed. FR-028 is the whole contract. "
                "The header row is chosen by a heuristic - the row carrying the most <th> "
                "cells - and precision says so on every signal, which it did not before: the "
                "old string opened with 'exact', so a guess was published as an exact reading."
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        markup, overrides = _markup_of(record)
        if not markup.strip():
            return ()
        scanned = max(1, len(markup))
        found: list[RelationSignal] = []
        ordinal = 0
        for table_index, table in enumerate(_TABLE.finditer(markup)):
            label = overrides.get("table_label") or f"table{table_index}"
            headers, _header_row, rows = _read_table(table.group("rows"), table.start("rows"))
            pairing = _cells_with_headers(headers, rows)
            ragged = list(pairing.ragged)
            for header, value, row_index in pairing.paired:
                if is_empty(header[0]) or is_empty(value[0]):
                    continue
                subject, object_ref = _participants(header, value)
                found.append(
                    RelationSignal(
                        participants=(
                            RelationParticipant(
                                mention_ref=subject,
                                slot=ArgumentSlot(0),
                                role_hypothesis=HEADER_LABEL,
                                ordinal=0,
                                confidence=1.0,
                            ),
                            RelationParticipant(
                                mention_ref=object_ref,
                                slot=ArgumentSlot(1),
                                role_hypothesis=CELL_LABEL,
                                ordinal=1,
                                confidence=1.0,
                            ),
                        ),
                        kind=SignalKind.TABLE,
                        # The header, verbatim. The platform may later decide that 'CEO'
                        # means works_for; that decision belongs to a SemanticRegime and is
                        # recorded as a second reading, not smuggled in here.
                        relation_surface=cell_text(header[0]),
                        # `table_slot` and not `predicate_text`: there is no phrase between
                        # the ends to read. The header saying "Role" beside a cell saying
                        # "CEO" is a position in a grid, and a signal claiming to have read
                        # predicate words when it read a cell address is a record that
                        # misstates its own evidence.
                        basis=SignalBasis.TABLE_SLOT,
                        # Stated, not defaulted: markup states no proposition to deny.
                        polarity=Polarity.ASSERTED,
                        neighbourhood=Neighbourhood(
                            characters_scanned=scanned,
                            # The real enumeration: this producer pairs every header against
                            # every data row to decide which rows line up, and the number of
                            # such pairs is a number a reader can check against the table.
                            # The old value counted a cell *product* against a header, which
                            # is not what the pairing loop does.
                            pairs_considered=len(rows) * max(1, len(headers)),
                            scope_read=(
                                f"one <table> element ({len(rows)} data rows x "
                                f"{len(headers)} columns); no cross-table pair was considered"
                            ),
                            # **Not** "exact", and the leading word is the whole point: the
                            # header row is a heuristic choice, and a precision string that
                            # opens with "exact" makes a guess read as an exact reading.
                            precision=(
                                f"{PRECISION_HEURISTIC}; header row chosen by most <th> "
                                f"cells, ties to the earliest such row"
                            ),
                            notes=(
                                f"row {row_index}"
                                + (
                                    ""
                                    if not ragged
                                    else f"; {len(ragged)} row(s) not paired: "
                                    + "; ".join(row.describe() for row in ragged)
                                )
                            ),
                        ),
                        relation_ref=None,
                        # AMBIGUOUS, not a default. A header says what a column holds and
                        # not which end of the relation this cell is; choosing would be the
                        # platform inventing a reading the markup does not contain.
                        direction=DirectionHypothesis.AMBIGUOUS,
                        producer_ref=PRODUCER_REF,
                        producer_version=PRODUCER_VERSION,
                        context_ref=overrides.get("context_ref") or scope.context_ref,
                        semantic_regime_ref=(
                            overrides.get("semantic_regime_ref") or scope.semantic_regime_ref
                        ),
                        capture_ref=overrides.get("document_ref") or scope.document_ref,
                        # Exact about the table, silent about the world: the markup says
                        # this cell sits in this column, and no number could express what
                        # that means.
                        producer_confidence=1.0,
                        signal_ordinal=ordinal,
                        tenant_id=scope.tenant_id,
                        notes=f"{label} row {row_index}",
                        extra={
                            "table_label": label,
                            "column_header": cell_text(header[0]),
                            "cell_value": cell_text(value[0]),
                            "row_index": row_index,
                            "header_row_index": _header_row,
                            # The rows this table could not pair, named rather than
                            # dropped. Countable from the output, which is the property that
                            # matters: a loss with no trace is indistinguishable from a
                            # table that was well formed.
                            "ragged_row_indexes": [row.row_index for row in ragged],
                            "ragged_rows": [row.describe() for row in ragged],
                            "header_char_start": header[1],
                            "header_char_end": header[2],
                            "cell_char_start": value[1],
                            "cell_char_end": value[2],
                        },
                    )
                )
                ordinal += 1
        return tuple(found)


class ListExtractor:
    """Definition lists, as LIST signals: the term is the column header, the definition the cell.

    Shares :mod:`~extractors.signals.tables` because the shape that matters is identical -
    a key, a value, and no verb - and because the reasoning about what a key does and does
    not tell you is the same reasoning, so duplicating it would be duplicating the chance
    to get it wrong.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=LIST_PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.LIST,),
            reads=(
                "one <dl> element: each <dt> term with the <dd> definition beneath it. The "
                "term is the column header and the definition is the cell, exactly as in a "
                "table - a list is a table with no grid. A <dt> with no <dd> after it is "
                "read and reported as a term with no definition, not skipped: the pairing "
                "used to be zip(..., strict=False), which dropped the extra term and made a "
                "malformed definition list look like a well-formed one."
            ),
            cannot_read=(
                "what kind of thing the term names, and whether the definition is one value "
                "or several. A term is a label the document chose, not a field name from a "
                "schema, so it is read as prose and left for a later regime. It also cannot "
                "tell whether a <dt> with no <dd> means the definition was omitted or is on "
                "the next line, so it reports the term and declines to invent a definition."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None, for the same reason as the table producer. The "
                "basis is attribute_key, not predicate_text: a term beside its definition is "
                "a key/value pair, and there is no phrase between the two ends to read."
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        markup, overrides = _markup_of(record)
        if not markup.strip():
            return ()
        scanned = max(1, len(markup))
        label = overrides.get("list_label") or "list0"
        found: list[RelationSignal] = []
        ordinal = 0
        for list_match in _LIST.finditer(markup):
            base = list_match.start("items")
            terms = _spans(_DT, list_match.group("items"), base)
            definitions = _spans(_DD, list_match.group("items"), base)
            unpaired = _unpaired_terms(terms, definitions)
            for index, (term, definition) in enumerate(
                zip(terms, definitions, strict=False)
            ):
                if is_empty(term[0]) or is_empty(definition[0]):
                    continue
                subject, object_ref = _participants(
                    term, definition, labels=(TERM_LABEL, DEFINITION_LABEL)
                )
                found.append(
                    RelationSignal(
                        participants=(
                            RelationParticipant(
                                mention_ref=subject,
                                slot=ArgumentSlot(0),
                                role_hypothesis=TERM_LABEL,
                                ordinal=0,
                                confidence=1.0,
                            ),
                            RelationParticipant(
                                mention_ref=object_ref,
                                slot=ArgumentSlot(1),
                                role_hypothesis=DEFINITION_LABEL,
                                ordinal=1,
                                confidence=1.0,
                            ),
                        ),
                        kind=SignalKind.LIST,
                        relation_surface=cell_text(term[0]),
                        basis=SignalBasis.ATTRIBUTE_KEY,
                        polarity=Polarity.ASSERTED,
                        neighbourhood=Neighbourhood(
                            characters_scanned=scanned,
                            # The real enumeration: this producer pairs every term against
                            # the definition in its position, and the number of terms is the
                            # number of pairings decided.
                            pairs_considered=len(terms),
                            scope_read=(
                                f"one <dl> element ({len(terms)} terms, "
                                f"{len(definitions)} definitions); terms were paired "
                                "with definitions by position only, no term was compared "
                                "against any other, and no definition link was followed"
                            ),
                            precision=PRECISION_EXACT,
                            notes=(
                                f"term {index}"
                                + (
                                    ""
                                    if not unpaired
                                    else f"; {len(unpaired)} term(s) carried no definition "
                                    f"and are reported without one: " + "; ".join(unpaired)
                                )
                            ),
                        ),
                        relation_ref=None,
                        direction=DirectionHypothesis.AMBIGUOUS,
                        producer_ref=LIST_PRODUCER_REF,
                        producer_version=PRODUCER_VERSION,
                        context_ref=overrides.get("context_ref") or scope.context_ref,
                        semantic_regime_ref=(
                            overrides.get("semantic_regime_ref") or scope.semantic_regime_ref
                        ),
                        capture_ref=overrides.get("document_ref") or scope.document_ref,
                        producer_confidence=1.0,
                        signal_ordinal=ordinal,
                        tenant_id=scope.tenant_id,
                        notes=f"{label} term {index}",
                        extra={
                            "list_label": label,
                            "term": cell_text(term[0]),
                            "definition": cell_text(definition[0]),
                            "term_index": index,
                            "term_char_start": term[1],
                            "term_char_end": term[2],
                            "definition_char_start": definition[1],
                            "definition_char_end": definition[2],
                            # Reported, not dropped. `zip(..., strict=False)` discarded
                            # these, and a corpus with an unmatched <dt> produced output
                            # indistinguishable from a corpus without one.
                            "unpaired_term_indexes": _unpaired_indexes(terms, definitions),
                            "unpaired_terms": list(unpaired),
                        },
                    )
                )
                ordinal += 1
        return tuple(found)


def _read_table(
    rows_markup: str, base: int = 0
) -> tuple[list[_Cell], int, list[tuple[int, list[_Cell]]]]:
    """The header texts, the index of the row they came from, and the data rows.

    Header-ness is read from the **markup** - ``<th>`` versus ``<td>`` - and not
    reconstructed from a cell's text afterwards, because ``<th>`` is the only thing in the
    document that says a cell is a header. Inferring it from position or from capitalisation
    would be the platform deciding what the markup said.

    The header is taken from the first row that *contains* a ``<th>``, not from the first
    row. Those differ in real markup - a table with a spanning caption puts ``<th>`` in row
    one and the column names in row two - and assuming row one holds the column names is how
    a producer ends up reporting a caption as a column.

    **The header row is the row with the most ``<th>`` cells, and that is a heuristic -
    stated as one.** A table with a spanning caption puts a single ``<th colspan="3">`` in
    row one and the three column names in row two, and "the first row containing a ``<th>``"
    picks the caption. Counting ``<th>`` cells instead means one spanning cell loses to
    three column names, which is right for the markup anyone actually writes. It is not
    right for a table whose *only* header is a caption over one column, and that table
    reports no signals rather than reporting the caption as a column name - the failure mode
    chosen deliberately, since a missing signal is recoverable and a fabricated column is
    not. :attr:`~extractors.signals.signal.Neighbourhood.precision` records the heuristic
    on every signal this producer emits.

    **The header row's index is returned because the header row is not data.** A row that
    supplied the headers is excluded from the data rows, and that exclusion is the whole
    reason this function returns three things rather than two. Without it the header cells
    are emitted as values - ``Name | Role | Since`` becomes three more signals whose
    participants are the words "Name", "Role" and "Since" - which is a set of statements
    about the document that is confidently false, and the cheapest kind to produce, because
    the output still looks exactly like a table.

    ``base`` is where ``rows_markup`` begins in the caller's own string, and every cell's
    reported position is absolute. Phase 4B added it: a participant address carrying no
    position cannot tell two cells reading the same words from one cell read twice, and
    "Acme" appearing in row 1 and row 4 of one table was one participant.
    """
    parsed: list[tuple[int, list[_Cell], list[_Cell]]] = []
    for index, row in enumerate(_ROW.finditer(rows_markup)):
        cells_start = base + row.start("cells")
        texts: list[_Cell] = []
        header_texts: list[_Cell] = []
        for cell in _CELL.finditer(row.group("cells")):
            cell_start = cells_start + cell.start("text")
            span = (cell_text(cell.group("text")), cell_start, cells_start + cell.end("text"))
            texts.append(span)
            if cell.group(0).lower().startswith("<th"):
                header_texts.append(span)
        if not any(text for text, _start, _end in texts):
            continue
        parsed.append((index, texts, header_texts))

    with_th = [row for row in parsed if row[2]]
    if not with_th:
        return [], -1, [(index, texts) for index, texts, _ in parsed]
    # Most `<th>` cells wins; ties go to the earliest such row, so the choice is
    # deterministic rather than dependent on dict or set ordering.
    best = max(len(row[2]) for row in with_th)
    header_row_index, _header_all, header_names = next(
        row for row in with_th if len(row[2]) == best
    )
    header_texts = [text for text in header_names if text[0]]
    rows: list[tuple[int, list[_Cell]]] = []
    for index, texts, _ in parsed:
        if index == header_row_index:
            # A row that mixes `<th>` and `<td>` is both the header and data; its `<td>`
            # cells stay in the data rows rather than being dropped with the header.
            if len(texts) > len(header_names):
                remainder = [text for text in texts if text not in header_names]
                if remainder:
                    rows.append((index, remainder))
            continue
        rows.append((index, texts))
    return header_texts, header_row_index, rows


@dataclass(frozen=True, slots=True)
class _Pairing:
    """What one table's headers and rows yielded: what paired, and what did not."""

    paired: tuple[tuple[_Cell, _Cell, int], ...] = ()
    ragged: tuple[_RaggedRow, ...] = ()


def _cells_with_headers(
    headers: list[_Cell], rows: list[tuple[int, list[_Cell]]]
) -> _Pairing:
    """Every ``(header, cell, row index)`` in the table, positionally paired - and the
    rows that would not pair, **named**.

    Positional, and that is a real limitation rather than a shortcut: a table with merged
    cells has fewer cells in a row than headers in the row above, and pairing them by
    position would attach a value to the wrong column. A row whose width does not match the
    header's is therefore **not paired**, because emitting a cell under a header the markup
    never put it in is a confident falsehood about the document's own structure - the
    cheapest kind of falsehood to produce and the hardest to notice, because the output
    still looks like a table.

    What Phase 4B changed is not the decision but the **silence**. Before it, a ragged row
    was skipped and the record said nothing at all, so three cells of a real table went
    missing with no trace and a corpus containing one looked exactly like a corpus that did
    not. Now every skipped row is returned as a :class:`_RaggedRow` and reaches the signal
    in ``extra["ragged_rows"]`` and in the neighbourhood's notes, which makes the loss
    countable (FR-095). The pairing ``zip`` is ``strict=True`` for the rows that *do* line
    up: the widths have already been compared, and a silent truncation there would be the
    same defect one layer in.
    """
    if not headers:
        return _Pairing()
    pairs: list[tuple[_Cell, _Cell, int]] = []
    ragged: list[_RaggedRow] = []
    for row_index, row in rows:
        if len(row) != len(headers):
            ragged.append(_RaggedRow(row_index, len(headers), len(row)))
            continue
        for header, value in zip(headers, row, strict=True):
            pairs.append((header, value, row_index))
    return _Pairing(tuple(pairs), tuple(ragged))


def _spans(pattern: re.Pattern[str], markup: str, base: int) -> list[_Cell]:
    """Every ``pattern`` match's visible text and its absolute span, in order."""
    return [
        (cell_text(match.group("text")), base + match.start("text"), base + match.end("text"))
        for match in pattern.finditer(markup)
    ]


def _unpaired_terms(terms: list[_Cell], definitions: list[_Cell]) -> list[str]:
    """The ``<dt>`` terms with no ``<dd>`` after them, described.

    This is what ``zip(terms, definitions, strict=False)`` threw away. The pairing loop
    still stops at the shorter of the two - a signal needs two ends, and a term with no
    definition has one - so the loss is unchanged and only its *visibility* is new: the
    caller sees the term's own words and its index, and can tell a document that wrote a
    dangling term from a producer that lost one.
    """
    if len(terms) <= len(definitions):
        return []
    return [
        f"term {index} ({text!r} at char {start}) carried no definition"
        for index, (text, start, _end) in enumerate(
            terms[len(definitions) :], len(definitions)
        )
    ]


def _unpaired_indexes(terms: list[_Cell], definitions: list[_Cell]) -> list[int]:
    if len(terms) <= len(definitions):
        return []
    return list(range(len(definitions), len(terms)))


def _participants(
    first: _Cell,
    second: _Cell,
    *,
    labels: tuple[str, str] = (HEADER_LABEL, CELL_LABEL),
) -> tuple[str, str]:
    """Two cells, as two deferred occurrence references.

    Both ends are the cells' **own visible text, whole, at their own offsets**. Before Phase
    4B this was ``header:<table>/<column>`` and ``cell:<table>:<value>``, and both halves of
    that were fabrications: a *column label* and a lowercased *cell value* standing where a
    mention belonged, with the value truncated nowhere but normalised to a case the document
    did not use. FR-094 is about exactly this - a field name or a property name posing as a
    thing in the world - and a table header is the purest instance of it in the package.

    A ``<th>``'s own text is a real occurrence in the document, so addressing it is honest,
    and addressing it at its own position is what stops two columns called ``Role`` in one
    table being one participant.
    """
    return (
        deferred_occurrence(label=labels[0], surface=first[0], start=first[1], end=first[2]),
        deferred_occurrence(label=labels[1], surface=second[0], start=second[1], end=second[2]),
    )


def _markup_of(record: object) -> tuple[str, Mapping[str, str]]:
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        text = str(record.get("html") or record.get("markup") or record.get("text") or "")
        overrides = {
            key: str(record[key])
            for key in (
                "context_ref",
                "semantic_regime_ref",
                "document_ref",
                "table_label",
                "list_label",
            )
            if record.get(key)
        }
        return text, overrides
    return "", {}


def table_signals(tables: list[object], *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
    """Drive the table producer over a list of ``<table>`` elements."""
    from extractors.signals.protocol import run_producer

    return run_producer(TableExtractor(), tables, scope=scope)


def list_signals(lists: list[object], *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
    """Drive the list producer over a list of ``<dl>`` elements."""
    from extractors.signals.protocol import run_producer

    return run_producer(ListExtractor(), lists, scope=scope)


__all__ = [
    "CELL_LABEL",
    "DEFINITION_LABEL",
    "HEADER_LABEL",
    "INDEPENDENCE_FAMILY",
    "LIST_PRODUCER_REF",
    "MAX_PAIRS_CONSIDERED",
    "PRECISION_EXACT",
    "PRECISION_HEURISTIC",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "TERM_LABEL",
    "ListExtractor",
    "TableExtractor",
    "cell_text",
    "is_empty",
    "list_signals",
    "table_signals",
]
