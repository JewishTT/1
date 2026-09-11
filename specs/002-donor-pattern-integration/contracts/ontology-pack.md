# Ontology Pack Contract (kafSIEM pattern)

A versioned, registry-validated schema pack constraining the entity/property/relation space (FR-012, US5). Consumed by extractors and admission.

## OntologyPack

```text
OntologyPack {
  pack_id        // OP-<uuid>
  pack_version   // e.g. ontology-v3
  entity_types   // [PERSON, ORG, LOCATION, EMAIL, PHONE, DOMAIN, USERNAME, DOCUMENT, ...]
  properties     // admissible properties per type
  relations      // admissible relations / predicates
  status         // DRAFT -> REGISTERED -> ACTIVE
  registered_at
}
```

## Rules

- Extractors/admission consume only ACTIVE packs; a new pack version replaces the old without overwrite (reproducibility).
- Packs are schema/ontology declarations, not data — they constrain types/relations of statements and mentions.
- Ontology packs ship as versioned artifacts (Schema Registry-compatible); events and state carry refs, never blobs (I-5).
- Adding a new entity type requires a new pack version + extractor/admission support; no silent model changes.
- Packs are tenant-scoped like other operational state.