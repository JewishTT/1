"""Context Engine: durable research context as a first-class object (Feature 024 Phase 4/5).

Implements ``InvestigationContext``, the five separated components, the saturation
and frontier model, and replay.

Hermetic by construction: the engine is handed a store, and the only store used here
is in-memory, so every assertion runs with no database, no broker, and no clock.
"""