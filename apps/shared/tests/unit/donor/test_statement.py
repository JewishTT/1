from donor.statement import Statement


def test_make_key_is_deterministic() -> None:
    key_a = Statement.make_key("dataset1", "ent-1", "name", "John", False)
    key_b = Statement.make_key("dataset1", "ent-1", "name", "John", False)
    assert key_a == key_b
    assert len(key_a) == 40  # sha1 hex


def test_make_key_includes_value() -> None:
    a = Statement.make_key("d", "e", "name", "John", False)
    b = Statement.make_key("d", "e", "name", "Jane", False)
    assert a != b


def test_make_key_includes_lang() -> None:
    a = Statement.make_key("d", "e", "name", "John", False)
    b = Statement.make_key("d", "e", "name", "John", False, lang="en")
    assert a != b


def test_make_key_includes_external_flag() -> None:
    a = Statement.make_key("d", "e", "name", "John", True)
    b = Statement.make_key("d", "e", "name", "John", False)
    assert a != b


def test_make_key_returns_none_on_missing_prop_or_value() -> None:
    assert Statement.make_key("d", "e", None, "John", False) is None
    assert Statement.make_key("d", "e", "name", None, False) is None


def test_statement_generates_id_from_key_when_absent() -> None:
    stmt = Statement("ent-1", "name", "Person", "John", "dataset1")
    expected = Statement.make_key("dataset1", "ent-1", "name", "John", False)
    assert stmt.id == expected


def test_original_value_only_preserved_when_different() -> None:
    same = Statement("e", "name", "Person", "John", "d", original_value="John")
    assert same.original_value is None
    diff = Statement("e", "name", "Person", "John", "d", original_value="John Doe")
    assert diff.original_value == "John Doe"


def test_last_seen_defaults_to_first_seen() -> None:
    stmt = Statement("e", "name", "Person", "John", "d", first_seen="2026-01-01")
    assert stmt.last_seen == "2026-01-01"


def test_clone_keeps_id_when_overriding_unrelated_field() -> None:
    stmt = Statement("e", "name", "Person", "John", "d", first_seen="2026-01-01")
    cloned = stmt.clone(first_seen="2026-02-01")
    assert cloned.id == stmt.id


def test_clone_regenerates_id_when_value_changes() -> None:
    stmt = Statement("e", "name", "Person", "John", "d")
    cloned = stmt.clone(value="Jane")
    assert cloned.id != stmt.id
    assert cloned.value == "Jane"


def test_from_dict_round_trip() -> None:
    stmt = Statement("e", "name", "Person", "John", "d", external=True, origin="feed/a")
    as_dict = stmt.to_dict()
    restored = Statement.from_dict(as_dict)
    assert restored.to_dict() == stmt.to_dict()
    assert restored.id == stmt.id


def test_to_db_row_carries_prop_type() -> None:
    stmt = Statement("e", "name", "Person", "John", "d")
    row = stmt.to_db_row()
    assert "prop_type" in row
    assert row["external"] is False


def test_statements_compare_equal_by_id() -> None:
    a = Statement("e", "name", "Person", "John", "d")
    b = Statement.from_dict(a.to_dict())
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_statement_sorting_is_stable() -> None:
    a = Statement("e", "name", "Person", "John", "d")
    b = a.clone(value="Jane")
    c = a.clone(value="Zoe")
    ordered = sorted([c, a, b])
    assert ordered == sorted(ordered, key=lambda s: (s.prop != Statement.BASE, s.id or ""))