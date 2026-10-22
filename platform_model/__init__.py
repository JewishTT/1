"""Dynamic platform documentation generator.

Builds a machine-generated, AI-loadable model of the COGNITIVE platform from the
source tree (AST for Python, a lightweight parser for TypeScript/React, a
scanner for Rust) plus the semantic layer already produced by ``tools/specs/*``.

Nothing in the output is hand-written: every page is derived from the code, so
the documentation cannot drift from the thing it describes. ``--check`` fails
when the committed output no longer matches the tree, which is what turns the
model into a gate rather than a snapshot.
"""
