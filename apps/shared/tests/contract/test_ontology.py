"""Contract tests: ontology pack registry (T003, FR-012, kafSIEM pattern)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from events.ontology_pack import OntologyPack, OntologyPackRegistry, OntologyPackStatus


@pytest.mark.contract
class TestOntologyPack:
    def test_register_then_activate(self) -> None:
        registry = OntologyPackRegistry()
        pack = registry.register(OntologyPack(pack_version="ontology-v1"))
        assert pack.status == OntologyPackStatus.REGISTERED
        active = registry.activate("ontology-v1")
        assert active.status == OntologyPackStatus.ACTIVE
        assert registry.active_for() is pack

    def test_version_never_overwritten(self) -> None:
        registry = OntologyPackRegistry()
        registry.register(OntologyPack(pack_version="ontology-v1"))
        with pytest.raises(ValueError):
            registry.register(OntologyPack(pack_version="ontology-v1"))
        assert registry.versions() == ["ontology-v1"]

    def test_allows_type_case_insensitive(self) -> None:
        pack = OntologyPack(entity_types=["PERSON", "EMAIL"])
        assert pack.allows_type("email")
        assert pack.allows_type("PERSON")
        assert not pack.allows_type("ipv4")

    def test_unknown_version_rejected(self) -> None:
        registry = OntologyPackRegistry()
        with pytest.raises(KeyError):
            registry.activate("missing-pack")