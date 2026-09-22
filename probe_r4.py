# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\tim\Desktop\COGNITIVE\1")
sys.path.insert(0, str(ROOT / "apps" / "interpretation"))

out = []
ap = out.append

def A(x):
    return ascii(x)

from extractors.normalize import normalize_pass, normalize_person_name  # noqa: E402
from extractors.types import TypedMention  # noqa: E402

# exact co_occurrence ordering for both sides (ASCII-escaped, no mojibake)
ms = [
    TypedMention(kind="person", value="Сергей Иванов", extractor="persons", lang="ru"),
    TypedMention(kind="person", value="Ольга Петрова", extractor="persons", lang="ru"),
    TypedMention(kind="email", value="olga@example-petrova.ru", extractor="contacts", lang="ru"),
]
res = normalize_pass(ms)
by = {m.value: m for m in res}
for v in ("Сергей Иванов", "Ольга Петрова"):
    m = by[v]
    ev = m.evidence or {}
    ap("  %s" % A(v))
    for k in sorted(ev):
        val = ev[k]
        ap("     %s = %s" % (k, [A(x) for x in val] if isinstance(val, list) else A(val)))

ap("")
ap("  canonical('Ольга Петрова') = %s" % A(normalize_person_name("Ольга Петрова").canonical))
ap("  canonical('Сергей Иванов') = %s" % A(normalize_person_name("Сергей Иванов").canonical))

from extractors.language import pack_note  # noqa: E402

for lng in ("ru", "en", "zh", "zz"):
    ap("  pack_note %s = %r" % (lng, pack_note(lng)))

Path(r"C:\Users\tim\AppData\Local\Temp\opencode\coocc_exact.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
print("WROTE", len(out))
