from __future__ import annotations
from typing import Dict, Any
import hashlib, io, httpx, zipfile, xml.etree.ElementTree as ET
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

_MAX_BYTES = 15 * 1024 * 1024

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _pdf_meta(b: bytes) -> Dict[str, Any]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(b))
        info = reader.metadata or {}
        return {"type":"pdf","meta":{k.strip("/"): str(v) for k,v in info.items()}}
    except Exception:
        return {"type":"pdf","meta":{}}

def _image_exif(b: bytes) -> Dict[str, Any]:
    try:
        ex = {}
        img = Image.open(io.BytesIO(b))
        raw = img.getexif()
        if not raw: return {"type":"image","meta":{}}
        for tag_id, val in raw.items():
            tag = TAGS.get(tag_id, tag_id)
            ex[tag] = str(val)
        gps = ex.get("GPSInfo")
        if isinstance(gps, dict):
            flat = {}
            for k, v in gps.items():
                name = GPSTAGS.get(k, k)
                flat[name] = str(v)
            ex["GPSInfo"] = flat
        return {"type":"image","meta":ex}
    except Exception:
        return {"type":"image","meta":{}}

def _docx_meta(b: bytes) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            with z.open("docProps/core.xml") as f:
                root = ET.fromstring(f.read())
        ns = {
            "cp":"http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
            "dc":"http://purl.org/dc/elements/1.1/",
            "dcterms":"http://purl.org/dc/terms/",
        }
        meta = {}
        for tag in ("title","subject","creator","description"):
            el = root.find(f"dc:{tag}", ns)
            if el is not None and el.text: meta[tag] = el.text
        for tag in ("created","modified"):
            el = root.find(f"dcterms:{tag}", ns)
            if el is not None and el.text: meta[tag] = el.text
        return {"type":"docx","meta":meta}
    except Exception:
        return {"type":"docx","meta":{}}

def sniff_and_parse(content_type: str, data: bytes) -> Dict[str, Any]:
    ct = (content_type or "").lower()
    head = data[:8]
    if "pdf" in ct or head.startswith(b"%PDF"):
        return _pdf_meta(data)
    if "image" in ct or head.startswith((b"\xff\xd8", b"\x89PNG")):
        return _image_exif(data)
    if "officedocument.wordprocessingml" in ct or head.startswith(b"PK"):
        out = _docx_meta(data)
        if out["meta"]: return out
    return {"type":"unknown","meta":{}}

async def extract_metadata_from_url(url: str, *, timeout=15.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.content[:_MAX_BYTES]
        out = sniff_and_parse(r.headers.get("Content-Type",""), data)
        out["sha256"] = _sha256(data)
        out["url"] = url
        return out

