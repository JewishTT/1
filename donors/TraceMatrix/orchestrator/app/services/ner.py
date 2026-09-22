import os
from typing import Dict, List

class NER:
    def __init__(self, model_name: str | None = None):
        self.enabled = True
        self.model_name = model_name or os.getenv("SPACY_MODEL", "en_core_web_sm")
        try:
            import spacy  # noqa
            self._spacy = spacy.load(self.model_name)
        except Exception:
            self.enabled = False
            self._spacy = None

    def extract(self, text: str) -> Dict[str, List[str]]:
        out = {"person": [], "org": [], "gpe": [], "date": []}
        if not text:
            return out
        if self.enabled and self._spacy:
            doc = self._spacy(text)
            for ent in getattr(doc, "ents", []):
                label = (ent.label_ or "").upper()
                if label == "PERSON": out["person"].append(ent.text)
                elif label in ("ORG","FAC"): out["org"].append(ent.text)
                elif label in ("GPE","LOC"): out["gpe"].append(ent.text)
                elif label in ("DATE","TIME"): out["date"].append(ent.text)
        for k in out: out[k] = sorted(set(out[k]))
        return out

