import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("apps/control-plane", "apps/shared", "apps/interpretation", "apps/admission", "apps/projection", "apps/science", "apps/acquisition", "apps/zero", "apps/feedback", "apps/specops"):
    sys.path.insert(0, str(ROOT / p))

from db.schema import ENTITY_TYPE_VALUES  # noqa: E402
from services.tool_catalog import infer_entity_type  # noqa: E402

identities = [
    {"account": "alpha"},
    {"account": "Pulse"},
    {"domain": "example.com"},
    {"email": "a@b.c"},
    {"name": "Gazprom Neft"},
    {"phone": "+10000000000"},
    {"handle": "@x"},
    {"ip": "1.2.3.4"},
    {"mystery": "value"},
    {},
]
for identity in identities:
    label = infer_entity_type(identity)
    ok = label in ENTITY_TYPE_VALUES
    print(f"{identity!r:40} -> {label!r:22} valid={ok}")
