
from typing import List
from rapidfuzz import fuzz

DEFAULT_KEYWORDS = ["architect","αρχιτέκτονας","architecture","studio","portfolio","BIM","TEE","CAD"]

def matches_profession(text: str, keywords: List[str] = None, threshold: int = 70) -> bool:
    if not text: return False
    kws = keywords or DEFAULT_KEYWORDS
    tl = text.lower()
    for kw in kws:
        if kw.lower() in tl: return True
    for kw in kws:
        if fuzz.partial_ratio(tl, kw.lower()) >= threshold:
            return True
    return False
