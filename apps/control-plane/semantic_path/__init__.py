"""Composition root for multi-app deterministic pipelines.

Unlike ``apps/shared`` (a base value layer) and the per-capability apps, a module
here may depend on more than one of them. That is the point: the semantic
execution path in :mod:`pipeline.semantic_path` runs extraction, the semantic
fabric, the relation store and the graph projection in one pass, and putting it
anywhere lower in the dependency graph would have inverted the declared
direction -- ``apps/shared`` must not know that ``apps/interpretation`` or
``apps/projection`` exist, because both of them are built on top of it.

This is the same role ``application/entities.py`` already plays when it reaches
into ``projection.temporal_materialization``.
"""
