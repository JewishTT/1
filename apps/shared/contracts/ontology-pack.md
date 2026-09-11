# Ontology pack contract (kafSIEM pattern)

Authoritative contract: [`specs/002-donor-pattern-integration/contracts/ontology-pack.md`](../../../specs/002-donor-pattern-integration/contracts/ontology-pack.md).

Versioned ontology/schema packs: entity types, properties, relations (FR-012).
Packs move DRAFT → REGISTERED → ACTIVE and are never overwritten.
Implementation: `apps/shared/events/ontology_pack.py::OntologyPack`/`OntologyPackRegistry`,
consumed by `apps/interpretation/extractors/registry.py` (admissible-type filter);
Postgres table `ontology_packs`.