"""Real GLiNER RelEx smoke over a public, deterministic sentence from the upstream example.

This is an executable model check, not a fake: CI installs the optional upstream package and
downloads the small public ReLEx checkpoint. The output is retained as an Actions artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from extractors.signals.ml import GLiNERRelexExtractor, gliner_relex_signals
from extractors.signals.mentions import read_occurrence
from extractors.signals.protocol import ExtractionScope

TEXT = (
    "Bill Gates founded Microsoft in 1975. "
    "The company is headquartered in Redmond."
)
MODEL_REF = "knowledgator/gliner-relex-base-v1.0"


def main() -> int:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "artifacts/gliner-relex-smoke.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scope = ExtractionScope(
        tenant_id="ci-public-smoke",
        context_ref="CTX-gliner-smoke",
        semantic_regime_ref="REG-gliner-smoke",
        document_ref="CAP-gliner-smoke",
        investigation_id="CASE-gliner-smoke",
        recorded_by="github-actions",
    )
    extractor = GLiNERRelexExtractor.from_pretrained(
        MODEL_REF,
        entity_labels=("person", "organization", "date", "location"),
        relation_labels=("founded", "founded_in", "headquartered_in"),
        entity_threshold=0.4,
        relation_threshold=0.55,
    )
    report = extractor.report(TEXT, scope=scope)
    signals = gliner_relex_signals([TEXT], scope=scope, extractor=extractor)
    grounded = []
    for signal in signals:
        ends = []
        for participant in signal.participants:
            label, surface, span = read_occurrence(participant.mention_ref)
            if span is None or TEXT[span[0]:span[1]] != surface:
                raise RuntimeError("bound participant reference does not select source text")
            ends.append({"label": label, "surface": surface, "span": list(span)})
        if signal.relation_surface not in TEXT:
            raise RuntimeError("relation surface is not a literal source substring")
        grounded.append({
            "signal": signal.to_dict(),
            "participants": ends,
        })
    payload = {
        "model": MODEL_REF,
        "source_text": TEXT,
        "model_refusals": [item.to_dict() for item in report.refusals],
        "grounded_signal_count": len(grounded),
        "grounded_signals": grounded,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if not signals:
        raise RuntimeError(
            "the live GLiNER ReLEx checkpoint returned no relation with a predicate "
            "that could be grounded in the source sentence"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
