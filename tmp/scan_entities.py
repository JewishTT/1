import pathlib
import re

root = pathlib.Path("apps/control-plane")
print("=== SqlEntityStreamRepository methods ===")
text = (root / "db/entity_stream.py").read_text(encoding="utf-8")
for m in re.finditer(r"^\s*(?:async )?def (\w+)\(", text, re.M):
    print("  ", m.group(1))

print("=== 'correlations_for' anywhere in apps ===")
for p in pathlib.Path("apps").rglob("*.py"):
    if "donors" in p.parts:
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(t.splitlines(), 1):
        if "correlations_for" in line or "def correlations" in line:
            print(f"  {p.as_posix()}:{i}: {line.strip()[:120]}")

print("=== review store / _reviews ===")
for p in pathlib.Path("apps").rglob("*.py"):
    if "donors" in p.parts:
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(t.splitlines(), 1):
        if re.search(r"class .*Review|_reviews|review_store|ReviewStore", line):
            print(f"  {p.as_posix()}:{i}: {line.strip()[:130]}")

print("=== entities.py: module-level names (imports + defs) ===")
text = (root / "api/routes/entities.py").read_text(encoding="utf-8")
for i, line in enumerate(text.splitlines(), 1):
    if re.match(r"^(import |from |def |class |_[a-z_]+ =)", line):
        print(f"  {i}: {line.strip()[:120]}")
