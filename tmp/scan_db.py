import pathlib
import re

targets = [
    "apps/control-plane/db/session.py",
    "apps/control-plane/db/migrations/env.py",
    "apps/control-plane/api/routes/entities.py",
]
for name in targets:
    p = pathlib.Path(name)
    print("=" * 20, name, "exists" if p.exists() else "MISSING")
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    if name.endswith("entities.py"):
        lines = text.splitlines()
        print("\n".join(f"{i} {l}" for i, l in enumerate(lines[:70], 1)))
    else:
        print(text[:2500])

print("=" * 20, "DATABASE_URL / env references")
for p in sorted(pathlib.Path("apps").rglob("*.py")):
    if "donors" in p.parts:
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"DATABASE_URL|POSTGRES_|create_all|alembic", line):
            print(f"  {p.as_posix()}:{i}: {line.strip()[:130]}")
