"""The table and list producers: a document's own tabular structure, as it stands.

Feature 019, T028 (FR-028, SC-F).

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
PRODUCER_VERSION = "1"
INDEPENDENCE_FAMILY = "markup"

#: One table's headers and cells. Small, and stated: a producer scoped to one table reads
#: one table, so a document with 200 tables is 200 calls and never one call that ranked
#: 40,000 cells.
MAX_PAIRS_CONSIDERED = 1024

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


def _mentions(table_label: str, column: str, value: str) -> tuple[str, str]:
    """Address a header and a cell as surfaces, without minting mention ids.

    Same rule as every other producer here: this layer is below mention extraction, so it
    cites what the document stated and lets the assembler resolve it. A ``cell:`` address is
    stable under re-parsing (same table, column and value) and stable across processes,
    which is what makes two producers reading the same table produce the same signal id -
    and therefore one observation rather than two.
    """
    key = f"{table_label}/{cell_text(column)}"
    return f"header:{key.lower()}", f"cell:{table_label.lower()}:{cell_text(value).lower()}"


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
                "column holds - the cell is the participant, not the relation."
            ),
            cannot_read=(
                "which column is the key, and whether a column is single-valued. A table's "
                "first column usually is the key and this producer does not care: it reads "
                "every header and marks each signal's direction AMBIGUOUS, because a header "
                "says what a column holds and not which end of a relation it is. It also "
                "cannot tell one multi-valued cell from two rows, and does not guess."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None. 'CEO' is the document's word and the platform "
                "has no operator for it; emitting works_for here would be a producer that "
                "had quietly acquired a vocabulary, and its output could not be re-derived "
                "from the table if that vocabulary changed. FR-028 is the whole contract."
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
            headers, _header_row, rows = _read_table(table.group("rows"))
            for header, value, row_index in _cells_with_headers(headers, rows):
                if is_empty(header) or is_empty(value):
                    continue
                subject, object_ref = _mentions(label, header, value)
                found.append(
                    RelationSignal(
                        subject_mention_ref=subject,
                        object_mention_ref=object_ref,
                        kind=SignalKind.TABLE,
                        # The header, verbatim. The platform may later decide that 'CEO'
                        # means works_for; that decision belongs to a SemanticRegime and is
                        # recorded as a second reading, not smuggled in here.
                        relation_surface=cell_text(header),
                        neighbourhood=Neighbourhood(
                            characters_scanned=scanned,
                            pairs_considered=max(1, len(rows) * max(1, len(headers))),
                            scope_read=(
                                f"one <table> element ({len(rows)} data rows x "
                                f"{len(headers)} columns); no cross-table pair was considered"
                            ),
                            precision="exact; header row chosen by most <th> cells (a heuristic)",
                            notes=f"row {row_index}",
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
                            "column_header": cell_text(header),
                            "cell_value": cell_text(value),
                            "row_index": row_index,
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
                "table - a list is a table with no grid."
            ),
            cannot_read=(
                "what kind of thing the term names, and whether the definition is one value "
                "or several. A term is a label the document chose, not a field name from a "
                "schema, so it is read as prose and left for a later regime."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes="relation_ref is always None, for the same reason as the table producer.",
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
            terms = [cell_text(m.group("text")) for m in _DT.finditer(list_match.group("items"))]
            definitions = [cell_text(m.group("text")) for m in _DD.finditer(list_match.group("items"))]
            for index, (term, definition) in enumerate(zip(terms, definitions, strict=False)):
                if is_empty(term) or is_empty(definition):
                    continue
                subject, object_ref = _mentions(label, term, definition)
                found.append(
                    RelationSignal(
                        subject_mention_ref=subject,
                        object_mention_ref=object_ref,
                        kind=SignalKind.LIST,
                        relation_surface=term,
                        neighbourhood=Neighbourhood(
                            characters_scanned=scanned,
                            pairs_considered=max(1, len(terms)),
                            scope_read=(
                                f"one <dl> element ({len(terms)} terms); terms were paired "
                                "with definitions by position only, no term was compared "
                                "against any other, and no definition link was followed"
                            ),
                            precision="exact",
                            notes=f"term {index}",
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
                        extra={"list_label": label, "term": term, "definition": definition},
                    )
                )
                ordinal += 1
        return tuple(found)


def _read_table(rows_markup: str) -> tuple[list[str], int, list[tuple[int, list[str]]]]:
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
    """
    parsed: list[tuple[int, list[str], list[str]]] = []
    for index, row in enumerate(_ROW.finditer(rows_markup)):
        texts: list[str] = []
        header_texts: list[str] = []
        for cell in _CELL.finditer(row.group("cells")):
            text = cell_text(cell.group("text"))
            texts.append(text)
            if cell.group(0).lower().startswith("<th"):
                header_texts.append(text)
        if not any(texts):
            continue
        parsed.append((index, texts, header_texts))

    with_th = [row for row in parsed if row[2]]
    if not with_th:
        return [], -1, [(index, texts) for index, texts, _ in parsed]
    # Most `<th>` cells wins; ties go to the earliest such row, so the choice is
    # deterministic rather than dependent on dict or set ordering.
    best = max(len(row[2]) for row in with_th)
    header_row_index, header_texts_only, header_names = next(
        row for row in with_th if len(row[2]) == best
    )
    headers = [text for text in header_names if text]
    rows: list[tuple[int, list[str]]] = []
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
    _ = header_texts_only
    return headers, header_row_index, rows


def _cells_with_headers(
    headers: list[str], rows: list[tuple[int, list[str]]]
) -> list[tuple[str, str, int]]:
    """Every ``(header, cell value, row index)`` in the table, positionally paired.

    Positional, and that is a real limitation rather than a shortcut: a table with merged
    cells has fewer cells in a row than headers in the row above, and pairing them by
    position would attach a value to the wrong column. A row whose width does not match the
    header's is therefore **skipped**, because emitting a cell under a header the markup
    never put it in is a confident falsehood about the document's own structure - the
    cheapest kind of falsehood to produce and the hardest to notice, because the output
    still looks like a table.
    """
    if not headers:
        return []
    pairs: list[tuple[str, str, int]] = []
    for row_index, row in rows:
        if len(row) != len(headers):
            continue
        for header, value in zip(headers, row, strict=True):
            pairs.append((header, value, row_index))
    return pairs


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
    "INDEPENDENCE_FAMILY",
    "LIST_PRODUCER_REF",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "ListExtractor",
    "TableExtractor",
    "cell_text",
    "is_empty",
    "list_signals",
    "table_signals",
]
