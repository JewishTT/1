import pathlib
import re

pattern = re.compile(r"[\"'](splink|h3|river|docling-core)[^\"']*[\"']")
for p in sorted(pathlib.Path(".").glob("**/pyproject.toml")):
    parts = set(p.parts)
    if parts & {"donors", ".venv", "tmp", "node_modules"}:
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    for m in pattern.finditer(text):
        print(p.as_posix(), "|", m.group(0))
