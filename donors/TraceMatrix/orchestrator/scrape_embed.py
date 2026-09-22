
from __future__ import annotations
import trafilatura, datetime
from typing import Dict, Any
from sentence_transformers import SentenceTransformer

_model = None
def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _model

def fetch_and_embed(url: str):
    downloaded = trafilatura.fetch_url(url)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) if downloaded else ""
    text = (text or "").strip()
    model = get_model()
    vec = model.encode([text or url])[0].tolist()
    return {"content": text, "vector": vec, "timestamp": datetime.datetime.utcnow().isoformat()}
