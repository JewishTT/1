"""The Airbyte-shaped record that used to arrive as a person and lose its ASN.

This is the concrete case that motivated ``apps/shared/domain/ontology.py``:
``{"registrar": "Gazprom Neft", "domain": "gazprom-neft.ru", "asn": 12345}``.
"""

from __future__ import annotations

import pytest

from domain.ontology import (
    EntityType,
    read_record,
    type_for_field,
    typed_mentions,
    untyped_values,
    validate,
)

RECORD = {
    "registrar": "Gazprom Neft",
    "domain": "gazprom-neft.ru",
    "asn": 12345,
}


def test_registrar_is_an_organisation_not_a_person() -> None:
    assert type_for_field("registrar") is EntityType.ORGANIZATION
    pairs = dict(typed_mentions(RECORD))
    assert ("Gazprom Neft") in pairs[EntityType.ORGANIZATION.value]
    assert pairs.get(EntityType.PERSON.value) is None


def test_asn_survives_as_an_identifier() -> None:
    """The number was previously dropped entirely. Losing an identifier loses a network."""
    pairs = typed_mentions(RECORD)
    assert (EntityType.IDENTIFIER.value, "12345") in pairs


def test_every_declared_field_yields_a_type() -> None:
    assert set(typed_mentions(RECORD)) == {
        (EntityType.ORGANIZATION.value, "Gazprom Neft"),
        (EntityType.DOMAIN.value, "gazprom-neft.ru"),
        (EntityType.IDENTIFIER.value, "12345"),
    }


def test_an_unmapped_field_is_reported_not_discarded() -> None:
    """P11: semantic uncertainty must not reduce structural observability."""
    record = {"registrar": "Gazprom Neft", "mystery_score": 0.7}
    pairs = dict(typed_mentions(record))
    assert pairs[EntityType.ORGANIZATION.value] == "Gazprom Neft"
    kept = untyped_values(record)
    assert [r.field for r in kept] == ["mystery_score"]
    assert kept[0].value_kept is True
    assert kept[0].declared is False


def test_type_is_never_guessed_from_the_value() -> None:
    """A person-shaped string in an org field stays an organisation."""
    pairs = typed_mentions({"registrar": "Vladimir Putin"})
    assert pairs == ((EntityType.ORGANIZATION.value, "Vladimir Putin"),)


def test_nested_object_is_descended_one_level() -> None:
    record = {"address": {"city": "Saint Petersburg", "postcode": "191000"}}
    pairs = dict(typed_mentions(record))
    assert pairs[EntityType.PLACE.value] == "Saint Petersburg"
    assert untyped_values(record)[0].field == "address.postcode"


@pytest.mark.parametrize(
    ("field", "value", "etype", "ok"),
    [
        ("domain", "gazprom-neft.ru", EntityType.DOMAIN, True),
        ("domain", "not a domain", EntityType.DOMAIN, False),
        ("email", "a@b.co", EntityType.EMAIL, True),
        ("email", "a@b", EntityType.EMAIL, False),
        ("ip", "8.8.8.8", EntityType.IP, True),
        ("wallet", "0x" + "a" * 40, EntityType.CRYPTO, True),
        ("handle", "@sechin", EntityType.HANDLE, True),
    ],
)
def test_shape_validation(field: str, value: str, etype: EntityType, ok: bool) -> None:
    assert validate(value, etype) is ok


def test_failed_validation_does_not_relabel_the_field() -> None:
    """Doubt in the value is not evidence about the type."""
    record = {"domain": "garbage"}
    reading = read_record(record)[0]
    assert reading.type is EntityType.DOMAIN
    assert reading.value == "garbage"


def test_float_and_bool_are_handled_without_inventing_text() -> None:
    record = {"score": 1.5, "flag": True, "empty": None, "nested": {"x": 1}}
    pairs = dict(typed_mentions(record))
    assert pairs == {(EntityType.IDENTIFIER.value, "score")} or EntityType.IDENTIFIER.value not in pairs
    assert untyped_values(record)[0].field == "score"
