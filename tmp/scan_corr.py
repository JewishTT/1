import pathlib
import re

for p in sorted(pathlib.Path("apps").rglob("*.py")):
    if "donors" in p.parts or "tests" in p.parts:
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    hits = [
        f"{i}: {line.strip()[:110]}"
        for i, line in enumerate(text.splitlines(), 1)
        if re.search(r"correlation", line, re.I)
    ]
    if hits:
        print("==", p.as_posix())
        for h in hits[:12]:
            print("   ", h)
