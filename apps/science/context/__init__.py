"""Context-locality substrate for the context engine (spec 025 §7, §10).

Spec 025 §3.2 defines a ``ContextCell`` as *a local section of information* and
§10 as a gluing rule with a cocycle-style consistency check, while ADR-0031
records the deliberate limit: the platform does **not** claim a sheaf library, a
topos, or a formal local-global theorem. What it claims is the discipline --
explicit scopes, recorded loss under restriction, and a refusal to glue what
does not agree.

This package holds that substrate. It lives under ``apps/science`` because
``LAYER_ORDER`` puts ``science`` above ``control-plane``: a layer imports only
downward, so the *algorithms* live here and ``control-plane`` -- the only writer
of durable context state (spec 025 plan.md) -- drives them. Nothing in this
package imports control-plane.
"""

from __future__ import annotations
