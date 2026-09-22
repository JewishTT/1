import os, csv
from typing import Iterable, Dict, Optional, Tuple, Any
from ..config import EXPORT_DIR

# Maltego 3rd-party table import:
#  - Row is Headers (required)
#  - (Optional) Row is Types — αν θες να χρησιμοποιήσει το 'type' για entity class
# Εμπλουτισμένο schema για εικόνες/έγγραφα
HEADER = [
    "type",
    "value",
    "title",
    "url",
    "source",
    "mime",
    "sha256",
    "exif_gps_lat",
    "exif_gps_lon",
]

def ensure_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)

def _row_base(
    typ: str,
    value: str,
    *,
    title: str = "",
    url: str = "",
    source: str = "web",
    mime: str = "",
    sha256: str = "",
    exif_gps_lat: str = "",
    exif_gps_lon: str = "",
) -> Dict:
    return {
        "type": typ,
        "value": value,
        "title": title,
        "url": url,
        "source": source,
        "mime": mime,
        "sha256": sha256,
        "exif_gps_lat": exif_gps_lat,
        "exif_gps_lon": exif_gps_lon,
    }

def row_url(url: str, *, title: str = "", source: str = "web", mime: str = "", sha256: str = "") -> Dict:
    return _row_base("maltego.URL", url, title=title, url=url, source=source, mime=mime, sha256=sha256)

def row_image(url: str, *, title: str = "", source: str = "web", mime: str = "image/jpeg",
              sha256: str = "", exif_gps_lat: str = "", exif_gps_lon: str = "") -> Dict:
    return _row_base("maltego.Image", url, title=title, url=url, source=source, mime=mime,
                     sha256=sha256, exif_gps_lat=exif_gps_lat, exif_gps_lon=exif_gps_lon)

def export_entities(rows: Iterable[Dict]) -> str:
    ensure_dir()
    path = os.path.join(EXPORT_DIR, "entities.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            # γράψε μόνο τα γνωστά headers (ασφαλές fallback)
            w.writerow({k: r.get(k, "") for k in HEADER})
    return path
