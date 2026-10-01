"""Cross-check the frontend's canonical material against the Python donor.

The donor is the authority: same material string ⇒ same digest, computed by
``domain.relation_identity.digest128`` and by Node's ``createHash``.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "shared"))

from domain.relation_identity import canonical_material, digest128  # noqa: E402

CASES = [
    # (a, b, kind, source, expected canonical material)
    ("ENT-1", "ENT-2", "possible_match", "CE-1"),
    ("ENT-2", "ENT-1", "possible_match", "CE-1"),
    ("ENT-1", "ENT-2", "assertion", "CE-1"),
    ("ENT-1", "ENT-2", "relationship", "works_for"),
    ("ENT-2", "ENT-1", "relationship", "works_for"),
    ("B", "A", "co_occurrence", "OBS-7"),
    ("A", "B", "co_occurrence", "OBS-7"),
    ("ИВАН", "ОРГАНИЗАЦИЯ", "relationship", "works_for"),
    ("ИВАН", "ОРГАНИЗАЦИЯ", "relationship", "employed_by"),
]

lines = []
for a, b, kind, source in CASES:
    mode = "undirected" if kind == "co_occurrence" else "directed"
    if mode == "undirected":
        material = {
            "mode": mode,
            "type": kind,
            "members": sorted({a, b}),
            "source": source,
        }
    else:
        material = {"mode": mode, "type": kind, "subject": a, "object": b, "source": source}
    text = canonical_material(material)
    lines.append(
        {
            "a": a,
            "b": b,
            "kind": kind,
            "source": source,
            "material": text,
            "digest": digest128(text),
        }
    )

print(json.dumps(lines, ensure_ascii=False, indent=2))
