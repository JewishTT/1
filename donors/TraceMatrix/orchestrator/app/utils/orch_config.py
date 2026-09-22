import os, re, json, datetime as dt
from typing import Any, Dict
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

_env_pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")

def _env_expand(value: str) -> str:
    def repl(m):
        return os.getenv(m.group(1), "")
    return _env_pattern.sub(repl, value)


def load_yaml(path: str) -> Dict[str, Any]:
    if not Path(path).exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML not installed. Please add 'pyyaml' to requirements.")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    s = json.dumps(data)
    s = _env_expand(s)
    return json.loads(s)


def filename_from_template(tpl: str, name: str) -> str:
    now = dt.datetime.utcnow()
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "run").lower()).strip("-")
    return (
        tpl.replace("{yyyy}", f"{now.year:04d}")
        .replace("{mm}", f"{now.month:02d}")
        .replace("{dd}", f"{now.day:02d}")
        .replace("{HH}", f"{now.hour:02d}")
        .replace("{MM}", f"{now.minute:02d}")
        .replace("{SS}", f"{now.second:02d}")
        .replace("{slug(name)}", slug)
    )

